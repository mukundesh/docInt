import logging
import sys
from itertools import groupby
from pathlib import Path

from ..table import Cell, Row, Table
from ..util import load_config, read_config_from_disk
from ..vision import Vision


@Vision.factory(
    "table_finder",
    default_config={
        "doc_confdir": "conf",
        "conf_stub": "table_finder",
        "num_slots": 1000,
        "x_range": [0.3, 0.6],
        "sent_delim": ".;",
        "unicode_file": "conf/unicode.yml",
    },
)
class TableFinder:
    def __init__(
        self,
        doc_confdir,
        conf_stub,
        num_slots,
        x_range,
        sent_delim,
        unicode_file,
    ):
        self.doc_confdir = doc_confdir
        self.conf_stub = conf_stub
        self.sent_delim = sent_delim
        self.num_slots = num_slots
        self.x_range = x_range
        self.unicode_file = Path(unicode_file)

        s, e = int(x_range[0] * num_slots), int(x_range[1] * num_slots)
        self.x_range_slice = slice(s, e)

        self.unicode_dict = read_config_from_disk(self.unicode_file)

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

    def find_cell_boundary(self, list_item, path):
        def fill_slots(slots, word):
            min_sidx, max_sidx = int(word.xmin * len(slots)), int(
                word.xmax * len(slots)
            )
            max_sidx = min(max_sidx, len(slots) - 1)
            for sidx in range(min_sidx, max_sidx + 1):
                slots[sidx] += 1

        num_slots = self.num_slots
        slots = [0] * num_slots  # each slot captures word depth
        [fill_slots(slots, word) for word in list_item.words]

        enum_slots = list(enumerate(slots))[self.x_range_slice]
        gb = groupby(enum_slots, key=lambda tup: tup[1] == 0)

        empty_ranges = []
        for is_empty, empty_slots in gb:
            empty_slots = list(empty_slots)
            if is_empty and empty_slots:
                empty_ranges.append([empty_slots[0][0], empty_slots[-1][0] + 1])

        if not empty_ranges:
            return None

        empty_range = max(empty_ranges, key=lambda r: r[1] - r[0])
        empty_range = (
            (empty_range[0] - 5) / len(slots),
            (empty_range[1] + 5) / len(slots),
        )
        return empty_range

    def get_boundary_word(self, list_item, boundary_texts):
        prev_word = None
        for text, word in list_item.iter_word_text():
            no_punct_text = text.strip("-: ")
            if no_punct_text in boundary_texts:
                return word

            prev_word = word  # noqa: F841
        return None

    def find_inpage(self, page, list_items, boundary_texts, boundary_words, page_path):
        def split_words(words, x_range):
            lt_range, rt_range = (0.0, x_range[0]), (x_range[1], 1.0)
            lt_words = [w for w in words if w.box.in_xrange(lt_range, partial=True)]
            rt_words = [w for w in words if w.box.in_xrange(rt_range, partial=True)]
            return lt_words, rt_words

        body_rows = []
        for idx, list_item in enumerate(list_items):
            path = f"{page_path}.li{idx}"
            missing_unicodes = list_item.make_ascii(self.unicode_dict)  # noqa: F841

            if path == "pa3.li11":
                print("Found It")

            if path in boundary_words:
                boundary_word_path = boundary_words[path]
                boundary_word = page.doc.get_word(boundary_word_path)
                x_range = (boundary_word.xmin - 0.05, boundary_word.xmin)
            else:
                boundary_word = self.get_boundary_word(list_item, boundary_texts)
                if boundary_word is not None:
                    x_range = (boundary_word.xmin - 0.05, boundary_word.xmin)
                else:
                    x_range = self.find_cell_boundary(list_item, path)

            if not x_range:
                self.lgr.info(
                    f"> {path} ** No boundary, skipping >{list_item.raw_text()}<"
                )
                continue

            lt_words, rt_words = split_words(list_item.words, x_range)
            lt_cell, rt_cell = Cell.build(lt_words), Cell.build(rt_words)
            marker_cell = Cell.build(list_item.marker.words)
            m_str = list_item.marker.raw_text()
            self.lgr.info(f"> {path} {m_str}|{lt_cell.raw_text()}|{rt_cell.raw_text()}")

            body_rows.append(Row.build([marker_cell, lt_cell, rt_cell]))
        return Table.build(body_rows)

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"table_finder: {doc.pdf_name}")

        doc_config = load_config(self.doc_confdir, doc.pdf_name, self.conf_stub)
        boundary_words = doc_config.get("boundary_words", [])
        boundary_words = dict((c["list_path"], c["word_path"]) for c in boundary_words)

        boundary_texts = ["Minister", "Deputy", "Prime", "Mini", "VMinister"]

        doc.add_extra_page_field("tables", ("list", "docint.table", "Table"))
        doc.add_extra_page_field("heading", ("obj", "docint.region", "Region"))

        for page in doc.pages:
            if page.list_items:
                page_path = f"pa{page.page_idx}"
                table = self.find_inpage(
                    page, page.list_items, boundary_texts, boundary_words, page_path
                )
                page.tables = [table]
            else:
                page.tables = []

        self.remove_log_handler(doc)
        return doc


# /Users/mukund/Software/docInt/docint/pipeline/table_finder.py
