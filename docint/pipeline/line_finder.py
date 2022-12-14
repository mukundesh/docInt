import logging
import sys
from pathlib import Path

from ..page import Page
from ..region import Region
from ..util import load_config
from ..vision import Vision
from ..word_line import words_in_lines


@Vision.factory(
    "line_finder",
    default_config={
        "doc_confdir": "conf",
        "pre_edit": True,
        "newline_height_multiple": 1.0,
        "rotation_config": {
            "rotation_strategy": "none",
            "rotation_arg": None,
            "rotation_page_idxs": [],
            "rotation_min_angle": 0.05,
        },
        "conf_stub": "linefinder",
    },
)
class LineFinder:
    def __init__(
        self,
        doc_confdir,
        pre_edit,
        newline_height_multiple,
        rotation_config,
        conf_stub,
    ):
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.newline_height_multiple = newline_height_multiple
        self.rotation_config = rotation_config
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
        self.lgr.info(f"adding handler {log_path}")

        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def get_word_lines(self, page, angle, newline_height_multiple):
        print(f"nhm: {newline_height_multiple} angle: {angle} coords: {str(page.words[0].coords)}")
        if angle:
            rota_page = Page.build_rotated(page, angle)
            word_lines = words_in_lines(rota_page, newline_height_multiple=newline_height_multiple)
            page_word_lines = [[page.words[w.word_idx] for w in wl] for wl in word_lines]
            print(f"nhm: {newline_height_multiple} angle: {angle} coords: {str(page.words[0].coords)}")
            return page_word_lines
        else:
            return words_in_lines(page, newline_height_multiple=newline_height_multiple)

    def load_config(self, doc):
        doc_config = load_config(self.doc_confdir, doc.pdf_name, self.conf_stub)
        self.old_nhm = nhm = self.newline_height_multiple
        self.newline_height_multiple = doc_config.get("newline_height_multiple", nhm)
        return doc_config

    def teardown_config(self):
        self.newline_height_multiple = self.old_nhm

    def get_page_angle(self, page, cfg):
        if "scopes" in cfg:
            for scope in cfg["scopes"]:
                if page.path_abbr in scope.get("paths", []):
                    if scope["rotation_strategy"] == "num_markers":
                        return page.num_marker_angle
                    elif scope["rotation_strategy"] == "manual":
                        return scope["rotation_angle"]
                    else:
                        return 0.0
            return 0.0
        elif "rotation_strategy" in cfg:
            if cfg["rotation_strategy"] == "num_markers":
                return page.num_marker_angle
            elif cfg["rotation_strategy"] == "manual":
                return cfg["rotation_angle"]
            else:
                return 0.0
        elif self.rotation_config["rotation_strategy"] != "none":
            if self.rotation_config["rotation_strategy"] == "num_markers":
                return page.num_marker_angle
            elif self.rotation_config["rotation_strategy"] == "manual":
                return self.rotation_config["rotation_arg"]
            else:
                return 0.0

    def get_newline_height_multiple(self, page, cfg):
        return self.newline_height_multiple

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"line_finder: {doc.pdf_name}")
        cfg = self.load_config(doc)
        doc.add_extra_page_field("lines", ("list", "docint.region", "Region"))

        for page in doc.pages:
            angle = self.get_page_angle(page, cfg)
            newline_height_multiple = self.get_newline_height_multiple(page, cfg)
            word_lines = self.get_word_lines(page, angle, newline_height_multiple)
            page.lines = [Region.from_words(wl) for wl in word_lines if wl]

        self.teardown_config()
        self.remove_log_handler(doc)
        return doc
