import logging
import sys
from pathlib import Path

from ..region import Region
from ..util import load_config
from ..vision import Vision
from ..word_line import words_in_lines


@Vision.factory(
    "body_marker",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "bodymarker",
    },
)
class FindBodyMarker:
    def __init__(
        self,
        conf_dir,
        conf_stub,
    ):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = conf_stub

        self.lgr = logging.getLogger(f"docint.pipeline.{self.conf_stub}")
        self.lgr.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)

        self.file_handler = None

    def add_log_handler(self, doc):
        handler_name = f"{doc.pdf_name}.{self.conf_stub}.log"
        log_path = Path("logs") / handler_name
        self.file_handler = logging.FileHandler(log_path, mode="w")
        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"num_marker: {doc.pdf_name}")

        doc.add_extra_page_field("list_items", ("list", "docint.region", "Region"))

        doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)
        edits = doc_config.get("edits", [])
        if edits:
            print(f"Edited document: {doc.pdf_name}")
            doc.edit(edits)

        first_page = doc.pages[0]
        body_marker = first_page.layoutlm.get("ORDERBODY", [])

        nl_ht_multiple = doc_config.get("newline_height_multiple", 1.0)
        word_lines = words_in_lines(first_page, newline_height_multiple=nl_ht_multiple, para_indent=True)

        bm_idxs = set(w.word_idx for w in body_marker.words)
        bm_lines = [[w for w in line if w.word_idx in bm_idxs] for line in word_lines]

        lines_with_words = [idx for (idx, line) in enumerate(bm_lines) if line]
        bm_lines = bm_lines[lines_with_words[0] : lines_with_words[-1] + 1]  # noqa: E203

        body_marker = Region.build_with_lines(body_marker.words, bm_lines)

        first_page.list_items = [body_marker]
        self.remove_log_handler(doc)
        return doc
