import json
import logging
import sys
from pathlib import Path

from ..page import Page
from ..region import Region
from ..util import load_config
from ..vision import Vision
from ..word_line import words_in_lines, words_in_lines_short


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
        "keep_empty_lines": False,
        "output_dir": "output",
        "quick": False,
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
        keep_empty_lines,
        output_dir,
        quick,
    ):
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.newline_height_multiple = newline_height_multiple
        self.rotation_config = rotation_config
        self.conf_stub = conf_stub
        self.keep_empty_lines = keep_empty_lines
        self.output_dir = Path(output_dir)
        self.quick = quick

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
        # self.lgr.info(f"adding handler {log_path}")

        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def get_word_lines(self, page, angle, newline_height_multiple):
        if not page.words:
            return []

        # print(
        #     f"nhm: {newline_height_multiple} angle: {angle} coords: {str(page.words[0].coords)} >>>"
        # )
        if angle:
            rota_page = Page.build_rotated(page, angle)
            word_lines = words_in_lines(
                rota_page, newline_height_multiple=newline_height_multiple, is_page=True
            )
            page_word_lines = [[page.words[w.word_idx] for w in wl] for wl in word_lines]
            print(
                f"nhm: {newline_height_multiple} angle: {angle} coords: {str(page.words[0].coords)} <<<"
            )
            return page_word_lines
        else:
            if self.quick:
                return words_in_lines_short(
                    page.words, newline_height_multiple=newline_height_multiple
                )
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
        cfg = self.load_config(doc)

        edits = cfg.get("edits", [])
        if edits:
            print(f"Edited document: {doc.pdf_name}")
            doc.edit(edits)

        doc.add_extra_page_field("lines", ("list", "docint.region", "Region"))
        doc.add_extra_page_field("page_rota_angle", ("noparse", "", ""))

        json_path = self.output_dir / f"{doc.pdf_name}.{self.conf_stub}.json"
        if json_path.exists():
            jd = json.loads(json_path.read_text())
            for page, lines_word_idxs in zip(doc.pages, jd["lines_info"]):
                lines = [[page[idx] for idx in line_idxs] for line_idxs in lines_word_idxs]
                page.lines = [
                    Region.from_words(wl) if wl else Region.no_words(page.page_idx) for wl in lines
                ]

            self.teardown_config()
            return doc

        self.add_log_handler(doc)
        for page in doc.pages:
            angle = self.get_page_angle(page, cfg)
            newline_height_multiple = self.get_newline_height_multiple(page, cfg)
            word_lines = self.get_word_lines(page, angle, newline_height_multiple)
            if not self.keep_empty_lines:
                page.lines = [Region.from_words(wl) for wl in word_lines if wl]
            else:
                page.lines = [
                    Region.from_words(wl) if wl else Region.no_words(page.page_idx)
                    for wl in word_lines
                ]

            # write lines to log file
            for line_idx, line in enumerate(page.lines):
                self.lgr.debug(f"{page.page_idx}:{line_idx} {line.text_with_break()}")
            page.page_rota_angle = angle

        line_word_idxs = []
        for page in doc.pages:
            page_idxs = [[w.word_idx for w in line] for line in page.lines]
            line_word_idxs.append(page_idxs)
        json_path.write_text(json.dumps({"lines_info": line_word_idxs}))

        self.teardown_config()
        self.remove_log_handler(doc)
        return doc
