import io
import json
import pathlib

from google.protobuf.json_format import MessageToDict

from google.cloud import vision_v1
from google.cloud import storage

from ..vision import Vision
from ..page import Page
from ..word import Word
from ..shape import Coord, Poly


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
    def __init__(
        self, bucket, cloud_dir_path, output_dir_path, output_stub, overwrite_cloud
    ):

        self.bucket_name = bucket
        self.cloud_dir_path = cloud_dir_path
        self.output_dir_path = pathlib.Path(output_dir_path)
        self.output_stub = output_stub
        self.overwrite_cloud = overwrite_cloud

    def build_word(self, doc, page_idx, word_idx, ocr_word):
        coords = []
        for v in ocr_word["boundingBox"]["normalizedVertices"]:
            try:
                coords.append(Coord(v["x"], v["y"]))
            except KeyError:
                if not v:
                    coords.append(0.0, 0.0)
                elif "x" not in v and "y" in v:
                    coords.append(Coord(0.0, v["y"]))
                elif "y" not in v and "x" in v:
                    coords.append(Coord(v["x"], 0.0))
                else:
                    raise ValueError("Unknon vertex: " + str(v))
        shape = Poly(coords)

        text = "".join([c["text"] for c in ocr_word["symbols"]])

        last_symbol = ocr_word["symbols"][-1]
        break_type = (
            ""  # BreakType(last_symbol["property"].get("detectedBreak", "SPACE"))
        )
        return Word(doc, page_idx, word_idx, text, break_type, shape)

    def build_pages(self, doc, output_path):
        def get_words(pg):
            return [
                w for b in pg["blocks"] for p in b["paragraphs"] for w in p["words"]
            ]

        ocr_doc = json.loads(output_path.read_bytes())

        responses = ocr_doc["responses"]
        ocr_pages = [r["fullTextAnnotation"]["pages"][0] for r in responses]

        pages = []
        for (page_idx, ocr_page) in enumerate(ocr_pages):

            ocr_words = get_words(ocr_page)

            words = []
            for (word_idx, ocr_word) in enumerate(ocr_words):
                words.append(self.build_word(doc, page_idx, word_idx, ocr_word))

            width, height = ocr_page["width"], ocr_page["height"]
            page = Page(doc, page_idx, width, height)
            page.words = words
            doc.pages.append(page)
        return doc

    def run_sync_gcv(self, doc, output_path):
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
        requests = [
            {"input_config": input_config, "features": features, "pages": pages}
        ]
        response = image_client.batch_annotate_files(requests=requests)

        # get the protobuffer
        responsesDict = MessageToDict(response._pb)
        responseDict = responsesDict["responses"][0]
        output_path.write_text(json.dumps(responseDict))

    def run_async_gcv(self, doc, output_path):
        # https://cloud.google.com/vision/docs/pdf
        # https://cloud.google.com/vision/docs/reference/rest/v1/OutputConfig
        # TODO: better handling of operation failure/network failure

        if doc.num_pages > 2000:
            raise ValueError("Only < 2000 pages")

        mime_type = "application/pdf"
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(self.bucket_name)

        cloud_input_path = self.cloud_dir_path / "input" / doc.pdf_name
        input_blob = bucket.blob(str(cloud_input_path))
        if not input_blob.exists():
            input_blob.upload_from_filename(doc.pdf_path, content_type=mime_type)

        gcs_source_uri = "gs://{bucket_name}{cloud_input_path}"
        gcs_destination_uri = "gs://{bucket_name}{cloud_output_path}"
        batch_size = min(doc.num_pages, 100)

        image_client = vision_v1.ImageAnnotatorClient()
        feature = vision_v1.Feature(type_=vision_v1.Feature.Type.DOCUMENT_TEXT_DETECTION)
        gcs_source = vision_v1.GcsSource(uri=gcs_source_uri)
        input_config = vision_v1.InputConfig(gcs_source=gcs_source, mime_type=mime_type)

        gcs_destination = vision_v1.GcsDestination(uri=gcs_destination_uri)
        output_config = vision_v1.OutputConfig(
            gcs_destination=gcs_destination, batch_size=batch_size
        )

        async_request = vision_v1.AsyncAnnotateFileRequest(
            features=[feature], input_config=input_config, output_config=output_config
        )
        operation = image_client.async_batch_annotate_files(requests=[async_request])
        operation.result(timeout=420)

        # Once the request has completed and the output has been
        # written to GCS, we can list all the output files.
        # List objects with the given prefix.

        outputPrefix = str(self.output_dir_path)
        blob_list = list(bucket.list_blobs(prefix=outputPrefix))
        json_blobs = [b for b in blob_list if b.name.endswith("json")]

        for blob in json_blobs:
            with open(output_path, "w") as outputFile:
                outputFile.write(blob.download_as_string)

    def run_gcv(self, doc, output_path):
        storage_client = storage.Client()
        cloud_output_dir_path = (
            self.cloud_dir_path / pathlib.Path("output") / doc.pdf_stem
        )

        bucket = storage_client.get_bucket(self.bucket_name)
        output_blobs = list(bucket.list_blobs(prefix=str(cloud_output_dir_path)))
        output_jsons = [b for b in output_blobs if b.name.endswith("json")]

        if len(output_jsons) > 0 and not self.overwrite_cloud:
            if len(output_jsons) != 1:
                raise ValueError("Multiple files found, expecting on")

            output_path.write_text(output_jsons[0].download_as_string())
        else:
            if doc.num_pages < 5:
                self.run_sync_gcv(doc, output_path)
            else:
                self.run_batch_gcv(doc, output_path)

    def read_gcv(self, doc, output_path):
        return self.build_pages(doc, output_path)


    def __call__(self, doc):
        output_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"
        if output_path.exists():
            return self.read_gcv(doc, output_path)
        else:
            self.run_gcv(doc, output_path)
            return self.build_pages(doc, output_path)
