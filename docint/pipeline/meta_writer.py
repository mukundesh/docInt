import datetime
import json
import logging
import sys
from pathlib import Path

from pydantic import BaseModel

from docint.vision import Vision

# b /Users/mukund/Software/docInt/docint/pipeline/id_assigner.py:34

BLOCKSIZE = 2**10


class DocMeta(BaseModel):
    url: str
    pdf_repo_path: str
    download_time: datetime.datetime
    archive_url: str
    archive_time: datetime.datetime
    archive_sha: str
    archive_status_code: str
    sha_matched: bool

    @classmethod
    def get_relevant_objects(cls, doc_metas, path, shape):
        return doc_metas

    def get_html_json(self):
        return f"{{URL date: {str(self.archive_time)}, archive_sha: {self.archive_sha}, matched: {self.sha_matched} }}"  # noqa

    def get_svg_info(self):
        return {}


@Vision.factory(
    "meta_writer",
    default_config={
        "meta_file": "archive.json",
    },
)
class MetaWriter:
    def __init__(
        self,
        meta_file,
    ):
        self.meta_file = Path(meta_file)
        self.meta_dict = json.loads(self.meta_file.read_text())
        self.conf_stub = "metawriter"

        self.lgr = logging.getLogger(__name__)
        self.lgr.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(stream_handler)
        self.file_handler = None

    def add_log_handler(self, doc):
        handler_name = f"{doc.pdf_name}.{self.conf_stub}.log"
        log_path = Path("logs") / handler_name
        self.file_handler = logging.FileHandler(log_path, mode="w")
        self.lgr.info(f"adding handler {log_path}")

        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"meta_writer: {doc.pdf_name}")
        doc.add_extra_field("meta", ("obj", __name__, "DocMeta"))
        doc.meta = self.meta_dict[doc.pdf_name]
        self.remove_log_handler(doc)
        return doc
