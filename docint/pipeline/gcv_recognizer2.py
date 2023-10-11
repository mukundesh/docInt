import functools
import gzip
import io
import json
import statistics
from pathlib import Path

from more_itertools import first, flatten, partition

from ..doc import Doc
from ..page import Page
from ..pdfwrapper import open as pdf_open
from ..region import Region
from ..shape import Box, Coord, Poly
from ..util import avg
from ..vision import Vision
from ..word import BreakType, Word

# TODO 1: add config option wheter to save the output
# TODO 2: it fails the first time and once ocr is created then it is file
#         AttributeError: 'NoneType' object has no attribute 'read_bytes'
#         def get_ocr_pages(): ...
#             ...
#             ocr_doc = json.loads(o_path.read_bytes())


_break_type_dict = {
    "UNKNOWN": BreakType.Unknown,
    "SPACE": BreakType.Space,
    "SURE_SPACE": BreakType.Sure_space,
    "EOL_SURE_SPACE": BreakType.Eol_sure_space,
    "HYPHEN": BreakType.Hyphen,
    "LINE_BREAK": BreakType.Line_break,
    "NOT_PRESENT": BreakType.Not_present,
}


@Vision.factory(
    "gcv_recognizer2",
    depends=["google-cloud-vision", "google-cloud-storage"],
    is_recognizer=True,
    default_config={
        "bucket": "orgpedia",
        "cloud_dir_path": "recognizer",
        "output_dir_path": "output",
        "output_stub": "ocr",
        "overwrite_cloud": False,
        "check_stub_modified": "doc",  # this should be part of pipeline
        "process_page_image": False,
        "read_lines": False,
        "compress_output": False,
    },
)
class CloudVisionRecognizer2:
    def __init__(
        self,
        bucket,
        cloud_dir_path,
        output_dir_path,
        output_stub,
        overwrite_cloud,
        check_stub_modified,
        process_page_image,
        read_lines,
        compress_output,
    ):

        self.bucket_name = bucket
        self.cloud_dir_path = Path(cloud_dir_path)
        self.output_dir_path = Path(output_dir_path)
        self.output_stub = output_stub
        self.overwrite_cloud = overwrite_cloud
        self.check_stub_modified = check_stub_modified
        self.process_page_image = process_page_image
        self.read_lines = read_lines
        self.compress_output = compress_output

    def build_word(self, doc, page_idx, word_idx, ocr_word, page_size):
        coords = []
        if "normalizedVertices" in ocr_word["boundingBox"]:
            normalized = True
            vertices = ocr_word["boundingBox"]["normalizedVertices"]
        else:
            normalized = False
            width, height = page_size
            vertices = ocr_word["boundingBox"]["vertices"]

        for v in vertices:
            try:
                if normalized:
                    coords.append(Coord(x=v["x"], y=v["y"]))
                else:
                    coords.append(Coord(x=v["x"] / width, y=v["y"] / height))
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

        # gcv_break_type = (
        #     last_symbol.get("property", {"detectedBreak": {"type": "SPACE"}})
        #     .get("detectedBreak", {"type": "SPACE"})
        #     .get("type", "SPACE")
        # )

        gcv_break_type = (
            last_symbol.get("property", {"detectedBreak": {"type": "NOT_PRESENT"}})
            .get("detectedBreak")
            .get("type")
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

    def get_ocr_pages(self, output_path):
        output_paths = output_path if isinstance(output_path, list) else [output_path]
        for o_path in output_paths:

            if not o_path.exists() and Path(f"{str(output_path)}.gz").exists():
                o_path = Path(f"{str(output_path)}.gz")

            if o_path.suffix.lower() == ".gz":
                with gzip.open(o_path, "rb") as f:
                    ocr_doc = json.loads(f.read())
            else:
                print(o_path)
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

    def build_pages(self, doc, output_path):
        if not output_path:
            return doc

        print(output_path)

        def get_words(pg):
            if pg:
                return [w for b in pg["blocks"] for p in b["paragraphs"] for w in p["words"]]
            else:
                return []

        def is_small_word(word):
            return word.box.height < mean_height * 0.4

        for (page_idx, ocr_page) in enumerate(self.get_ocr_pages(output_path)):
            ocr_words = get_words(ocr_page)
            width, height = ocr_page.get("width", 0), ocr_page.get("height", 0)
            page_size = (width, height)

            page = doc.pages[page_idx]
            if self.process_page_image:
                # coordinate system is image based now !
                page.width, page.height = width, height
                page.page_image.page_width, page.page_image.page_height = width, height
                page.page_image.image_box = Box.from_bounding_box([0, 0, width, height])
                page.page_image.image_type = "raster"  # TODO CHANGE THIS TO ROTATED

            page_words = []
            for (word_idx, ocr_word) in enumerate(ocr_words):
                page_words.append(self.build_word(doc, page_idx, word_idx, ocr_word, page_size))

            mean_height = avg((w.box.height for w in page_words), default=0.02)
            keep_words, elim_words = partition(is_small_word, page_words)

            for (idx, word) in enumerate(keep_words):
                word.word_idx = idx
                page.words.append(word)

            print(f'Eliminate: >{"|".join(w.text for w in elim_words)}<')
        return doc

    def write_output_json(self, output_path, json_dict):
        if not isinstance(json_dict, dict):
            json_str = json_dict
            if not self.compress_output:
                output_path.write_bytes(json_str)
            else:
                with gzip.open(output_path, "wb") as f:
                    f.write(json_str)
        else:
            if not self.compress_output:
                output_path.write_text(json.dumps(json_dict, sort_keys=True, separators=(",", ":")))
            else:
                output_path = (
                    output_path if output_path.suffix.lower() == ".gz" else f"{str(output_path)}.gz"
                )
                with gzip.open(output_path, "wb") as f:
                    f.write(
                        bytes(
                            json.dumps(json_dict, sort_keys=True, separators=(",", ":")),
                            encoding="utf-8",
                        )
                    )

    def run_sync_gcv(self, doc, output_path):
        from google.cloud import vision
        from google.protobuf.json_format import MessageToDict

        if doc.num_pages > 5:
            raise ValueError("Only < 5 pages")

        image_client = vision.ImageAnnotatorClient()

        mime_type = "application/pdf"
        with io.open(doc.pdf_path, "rb") as f:
            content = f.read()

        input_config = {"mime_type": mime_type, "content": content}
        features = [{"type_": vision.Feature.Type.TEXT_DETECTION}]

        # The service can process up to 5 pages per document file. Here we specify
        # the first, second, and last page of the document to be processed.
        pages = list(range(1, doc.num_pages + 1))
        requests = [{"input_config": input_config, "features": features, "pages": pages}]
        response = image_client.batch_annotate_files(requests=requests, timeout=60)

        # get the protobuffer
        responsesDict = MessageToDict(response._pb)
        responseDict = responsesDict["responses"][0]
        self.write_output_json(output_path, responseDict)
        # output_path.write_text(json.dumps(responseDict, sort_keys=True, separators=(",", ":")))
        return output_path

    def run_sync_gcv_image(self, doc, output_path):
        from google.cloud import vision
        from google.protobuf.json_format import MessageToDict

        image_client = vision.ImageAnnotatorClient()

        mime_type = "image/tiff"
        all_responses_dict = {"responses": []}
        for (page_idx, page) in enumerate(doc.pages):
            print(f"Fetching image for page: {page_idx}")
            image_path = page.page_image.get_image_path()

            if image_path.suffix.lower() == ".png":
                pil_image = page.page_image.to_pil_image()
                tiff_in_mem = io.BytesIO()
                pil_image.save(tiff_in_mem, format="tiff")
                content = tiff_in_mem.getvalue()
            else:
                if image_path.stat().st_size > 41943040:
                    print("*** FAILED {doc.pdf_name}")
                    return None

                with io.open(page.page_image.get_image_path(), "rb") as f:
                    content = f.read()

            input_config = {"mime_type": mime_type, "content": content}
            features = [{"type_": vision.Feature.Type.TEXT_DETECTION}]

            pages = [1]
            requests = [{"input_config": input_config, "features": features, "pages": pages}]
            response = image_client.batch_annotate_files(requests=requests)

            # get the protobuffer
            responsesDict = MessageToDict(response._pb)
            responseDict = responsesDict["responses"][0]
            page_response = responseDict["responses"][0]
            page_response["context"] = {"pageNumber": page_idx + 1}
            all_responses_dict["responses"].append(page_response)
        self.write_output_json(output_path, all_responses_dict)
        return output_path

    def run_async_gcv(self, doc, num_pdf_pages):
        def get_json_blobs(prefix):
            prefix = str(prefix)
            prefix = prefix[:-4] if prefix.endswith("json") else prefix

            blob_list = list(bucket.list_blobs(prefix=prefix))
            json_blobs = [b for b in blob_list if b.name.endswith("json")]

            if len(json_blobs) == 1:
                return [(f"{doc.pdf_name}.ocr.json", json_blobs[0])]
            else:
                return [(Path(j.name).name.replace("jsonoutput-", ""), j) for j in json_blobs]

        def write_json_blobs(json_blobs):
            output_paths = []

            for file_name, json_blob in json_blobs:
                print(file_name)
                if self.compress_output and Path(file_name).suffix.lower() != ".gz":
                    file_name = f"{file_name}.gz"

                json_file_path = self.output_dir_path / file_name

                # json_file_path.write_bytes(json_blob.download_as_string())
                self.write_output_json(json_file_path, json_blob.download_as_string())

                output_paths.append(json_file_path)
            return output_paths

        # https://cloud.google.com/vision/docs/pdf
        # https://cloud.google.com/vision/docs/reference/rest/v1/OutputConfig
        # TODO: better handling of operation failure/network failure

        from google.cloud import storage, vision

        mime_type = "application/pdf"
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.bucket_name)

        cloud_input_path = self.cloud_dir_path / "input" / Path(doc.pdf_name)
        input_blob = bucket.blob(str(cloud_input_path))
        if not input_blob.exists():
            input_blob.upload_from_filename(doc.pdf_path, content_type=mime_type)
        gcs_source_uri = f"gs://{self.bucket_name}/{str(cloud_input_path)}"

        cloud_output_path = self.cloud_dir_path / "output" / f"{doc.pdf_name}.ocr.json"
        gcs_destination_uri = f"gs://{self.bucket_name}/{str(cloud_output_path)}"
        batch_size = min(num_pdf_pages, 100)

        # ocr output exists on cloud storage
        json_blobs = get_json_blobs(cloud_output_path)
        if json_blobs and self.overwrite_cloud:
            print("Reading from cloud storage")
            return write_json_blobs(json_blobs)

        image_client = vision.ImageAnnotatorClient()
        feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
        gcs_source = vision.GcsSource(uri=gcs_source_uri)
        input_config = vision.InputConfig(gcs_source=gcs_source, mime_type=mime_type)

        gcs_destination = vision.GcsDestination(uri=gcs_destination_uri)
        output_config = vision.OutputConfig(gcs_destination=gcs_destination, batch_size=batch_size)

        async_request = vision.AsyncAnnotateFileRequest(
            features=[feature], input_config=input_config, output_config=output_config
        )
        operation = image_client.async_batch_annotate_files(requests=[async_request])
        operation.result(timeout=420)

        # Once the request has completed and the output has been
        # written to GCS, we can list all the output files.
        # List objects with the given prefix.

        json_blobs = get_json_blobs(cloud_output_path)
        if json_blobs:
            return write_json_blobs(json_blobs)
        else:
            raise RuntimeError(f"{doc.pdf_name}: No output blobs found")

    def run_gcv(self, doc, num_pdf_pages):
        if self.process_page_image:
            print("IMAGES")
            output_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"
            return self.run_sync_gcv_image(doc, output_path)
        elif num_pdf_pages < 5:
            print("Running in sync")
            output_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"
            return self.run_sync_gcv(doc, output_path)
        elif num_pdf_pages > 2000:
            raise ValueError("Only < 2000 pages")
        else:
            print("Running in async")
            return self.run_async_gcv(doc, num_pdf_pages)

    def read_gcv(self, doc, output_path):
        return self.build_pages(doc, output_path)

    def __call__(self, doc):
        # output_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"
        print(f"Processing {doc.pdf_name}")

        output_paths = self.output_dir_path.glob(f"{doc.pdf_name}.{self.output_stub}.*json")
        output_paths = list(output_paths)

        if not output_paths:
            output_paths = self.output_dir_path.glob(f"{doc.pdf_name}.{self.output_stub}.*json.gz")

            def get_start_idx(p):
                if ".ocr." not in p.name:
                    return 0
                idxs = p.name.replace(doc.pdf_name, "").replace(".ocr.", "")
                if "-" in idxs:
                    s, rest = idxs.split("-", 1)
                    return int(s)
                else:
                    return 1

            output_paths = sorted(output_paths, key=get_start_idx)

        if self.read_lines:
            doc.add_extra_page_field("lines", ("list", "docint.region", "Region"))

        if output_paths and self.check_stub_modified:
            ocr_path = str(first(output_paths))
            doc_path = Path(ocr_path[: ocr_path.index(".ocr.")] + ".doc.json")
            if doc_path.exists():
                print("Reading doc.json")
                doc = Doc.from_disk(doc_path)
                doc.pipe_names[:-1] = []
                return doc

        if output_paths:
            print("Reading output_paths")
            return self.read_gcv(doc, output_paths)
        else:
            print(f"INSIDE GCV RECOGNIZER {doc.pdf_name}")
            pdf = pdf_open(doc.pdf_path)
            num_pdf_pages = len(pdf.pages)
            result = self.run_gcv(doc, num_pdf_pages)
            return self.build_pages(doc, result)
