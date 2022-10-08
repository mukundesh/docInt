import io
import json
import pathlib

from ..page import Page
from ..shape import Coord, Poly
from ..vision import Vision
from ..word import BreakType, Word

# TODO 1: add config option wheter to save the output
# TODO 2: it fails the first time and once ocr is created then it is file
#         AttributeError: 'NoneType' object has no attribute 'read_bytes'
#         def get_ocr_pages(): ...
#             ...
#             ocr_doc = json.loads(o_path.read_bytes())


_break_type_dict = {
    "UNKNOW": BreakType.Unknown,
    "SPACE": BreakType.Space,
    "SURE_SPACE": BreakType.Sure_space,
    "EOL_SURE_SPACE": BreakType.Eol_sure_space,
    "HYPHEN": BreakType.Hyphen,
    "LINE_BREAK": BreakType.Line_break,
}


@Vision.factory(
    "gcv_recognizer",
    default_config={
        "bucket": "orgpedia",
        "cloud_dir_path": "recognizer",
        "output_dir_path": "output",
        "output_stub": "ocr",
        "overwrite_cloud": False,
    },
)
class CloudVisionRecognizer:
    def __init__(self, bucket, cloud_dir_path, output_dir_path, output_stub, overwrite_cloud):

        self.bucket_name = bucket
        self.cloud_dir_path = pathlib.Path(cloud_dir_path)
        self.output_dir_path = pathlib.Path(output_dir_path)
        self.output_stub = output_stub
        self.overwrite_cloud = overwrite_cloud

    def build_word(self, doc, page_idx, word_idx, ocr_word):
        coords = []
        for v in ocr_word["boundingBox"]["normalizedVertices"]:
            try:
                coords.append(Coord(x=v["x"], y=v["y"]))
            except KeyError:
                if not v:
                    coords.append(0.0, 0.0)
                elif "x" not in v and "y" in v:
                    coords.append(Coord(x=0.0, y=v["y"]))
                elif "y" not in v and "x" in v:
                    coords.append(Coord(x=v["x"], y=0.0))
                else:
                    raise ValueError("Unknon vertex: " + str(v))
        shape = Poly(coords=coords)

        text = "".join([c["text"] for c in ocr_word["symbols"]])

        last_symbol = ocr_word["symbols"][-1]

        gcv_break_type = (
            last_symbol.get("property", {"detectedBreak": {"type": "SPACE"}})
            .get("detectedBreak", {"type": "SPACE"})
            .get("type", "SPACE")
        )
        break_type = _break_type_dict[gcv_break_type]
        return Word(
            doc=doc,
            page_idx=page_idx,
            word_idx=word_idx,
            text_=text,
            break_type=break_type,
            shape_=shape,
        )

    def build_pages(self, doc, output_path):
        def get_words(pg):
            if pg:
                return [w for b in pg["blocks"] for p in b["paragraphs"] for w in p["words"]]
            else:
                return []

        def get_ocr_pages(output_path):
            output_paths = output_path if isinstance(output_path, list) else [output_path]
            for o_path in output_paths:
                ocr_doc = json.loads(o_path.read_bytes())
                responses = ocr_doc["responses"]
                ocr_pages = []
                for r in responses:
                    if "fullTextAnnotation" in r:
                        ocr_pages.append(r["fullTextAnnotation"]["pages"][0])
                    else:
                        ocr_pages.append({})
                for ocr_page in ocr_pages:
                    yield ocr_page

        for (page_idx, ocr_page) in enumerate(get_ocr_pages(output_path)):
            ocr_words = get_words(ocr_page)

            words = []
            for (word_idx, ocr_word) in enumerate(ocr_words):
                words.append(self.build_word(doc, page_idx, word_idx, ocr_word))

            width, height = ocr_page.get("width", 0), ocr_page.get("height", 0)
            page = Page(doc=doc, page_idx=page_idx, words=words, width_=width, height_=height)
            doc.pages.append(page)
        return doc

    def run_sync_gcv(self, doc, output_path):
        from google.cloud import vision_v1
        from google.protobuf.json_format import MessageToDict

        if doc.num_pages > 5:
            raise ValueError("Only < 5 pages")

        image_client = vision_v1.ImageAnnotatorClient()

        mime_type = "application/pdf"
        with io.open(doc.pdf_path, "rb") as f:
            content = f.read()

        input_config = {"mime_type": mime_type, "content": content}
        features = [{"type_": vision_v1.Feature.Type.TEXT_DETECTION}]

        # The service can process up to 5 pages per document file. Here we specify
        # the first, second, and last page of the document to be processed.
        pages = list(range(1, doc.num_pages + 1))
        requests = [{"input_config": input_config, "features": features, "pages": pages}]
        response = image_client.batch_annotate_files(requests=requests)

        # get the protobuffer
        responsesDict = MessageToDict(response._pb)
        responseDict = responsesDict["responses"][0]
        output_path.write_text(json.dumps(responseDict))

    def run_async_gcv(self, doc, output_path):
        # https://cloud.google.com/vision/docs/pdf
        # https://cloud.google.com/vision/docs/reference/rest/v1/OutputConfig
        # TODO: better handling of operation failure/network failure

        from google.cloud import storage, vision_v1

        if doc.num_pages > 2000:
            raise ValueError("Only < 2000 pages")

        mime_type = "application/pdf"
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.bucket_name)

        cloud_input_path = self.cloud_dir_path / "input" / pathlib.Path(doc.pdf_name)
        input_blob = bucket.blob(str(cloud_input_path))
        if not input_blob.exists():
            input_blob.upload_from_filename(doc.pdf_path, content_type=mime_type)

        gcs_source_uri = f"gs://{self.bucket_name}/{str(cloud_input_path)}"

        cloud_output_path = self.cloud_dir_path / output_path
        gcs_destination_uri = f"gs://{self.bucket_name}/{str(cloud_output_path)}"
        batch_size = min(doc.num_pages, 100)

        image_client = vision_v1.ImageAnnotatorClient()
        feature = vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION)
        gcs_source = vision_v1.GcsSource(uri=gcs_source_uri)
        input_config = vision_v1.InputConfig(gcs_source=gcs_source, mime_type=mime_type)

        gcs_destination = vision_v1.GcsDestination(uri=gcs_destination_uri)
        output_config = vision_v1.OutputConfig(gcs_destination=gcs_destination, batch_size=batch_size)

        async_request = vision_v1.AsyncAnnotateFileRequest(
            features=[feature], input_config=input_config, output_config=output_config
        )
        operation = image_client.async_batch_annotate_files(requests=[async_request])
        operation.result(timeout=420)

        # Once the request has completed and the output has been
        # written to GCS, we can list all the output files.
        # List objects with the given prefix.

        outputPrefix = str(cloud_output_path)
        blob_list = list(bucket.list_blobs(prefix=outputPrefix))
        json_blobs = [b for b in blob_list if b.name.endswith("json")]

        if len(json_blobs) != 1:
            blob_names = ", ".join(b.name for b in json_blobs)
            print(f"Blobs found: {len(json_blobs)} >{blob_names}< {outputPrefix}")

            output_paths = []
            for blob in json_blobs:
                name = blob.name
                mid_fix = name[name.index('jsonoutput') + len('jsonoutput') + 1 : -5]

                output_name = f'{output_path.stem}-{mid_fix}-{output_path.suffix}'
                o_path = output_path.parent / output_name
                o_path.write_bytes(blob.download_as_string())
                output_paths.append(o_path)
            return output_paths
        else:
            output_path.write_bytes(json_blobs[0].download_as_string())
            return output_path

    def run_gcv(self, doc, output_path):
        from google.cloud import storage

        storage_client = storage.Client()
        cloud_output_dir_path = self.cloud_dir_path / pathlib.Path("output") / doc.pdf_stem

        bucket = storage_client.get_bucket(self.bucket_name)
        output_blobs = list(bucket.list_blobs(prefix=str(cloud_output_dir_path)))
        json_blobs = [b for b in output_blobs if b.name.endswith("json")]

        if len(json_blobs) > 0 and not self.overwrite_cloud:
            if len(json_blobs) != 1:
                json_blobs.sort(key=lambda b: b.name)
                blob_names = ", ".join(b.name for b in json_blobs)
                print(f"Blobs found: {len(json_blobs)} >{blob_names}<")

                output_paths = []
                for blob in json_blobs:
                    name = blob.name
                    mid_fix = name[name.index('jsonoutput') + len('jsonoutput') + 1 : -5]

                    output_name = f'{output_path.stem}-{mid_fix}{output_path.suffix}'
                    o_path = output_path.parent / output_name
                    o_path.write_bytes(blob.download_as_string())
                    output_paths.append(o_path)
                return output_paths
            else:
                output_path.write_bytes(json_blobs[0].download_as_string())
                return output_path
        else:
            if doc.num_pages < 5:
                print("Running in sync")
                return self.run_sync_gcv(doc, output_path)
            else:
                print("Running in async")
                return self.run_async_gcv(doc, output_path)

    def read_gcv(self, doc, output_path):
        return self.build_pages(doc, output_path)

    def __call__(self, doc):
        # output_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"

        output_paths = self.output_dir_path.glob(f"{doc.pdf_name}.{self.output_stub}*json")
        output_paths = list(output_paths)
        if output_paths:
            # print(f'Reading output_paths')
            return self.read_gcv(doc, output_paths)
        else:
            # imports are expensive
            # from google.protobuf.json_format import MessageToDict
            # from google.cloud import vision_v1
            # from google.cloud import storage
            output_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"

            result = self.run_gcv(doc, output_path)
            return self.build_pages(doc, result)
