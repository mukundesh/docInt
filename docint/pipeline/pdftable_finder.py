import logging
import sys
from pathlib import Path

import pdfplumber

from ..region import DataError
from ..shape import Box, Coord
from ..table import Cell, Row, Table
from ..util import load_config
from ..vision import Vision


@Vision.factory(
    "pdftable_finder",
    default_config={
        "pdfplumber_config": {"strategy": "lines"},
        "edit_doc": True,
        "skip_row_with_merged_cells": True,
        "header_row": "first_page_first_row",
        "conf_stub": "table",
        "log_level": "debug",
        "heading_offset": 50,
        "num_columns": 9,
    },
)
class PDFTableFinder:
    def __init__(
        self,
        pdfplumber_config,
        edit_doc,
        skip_row_with_merged_cells,
        header_row,
        conf_stub,
        log_level,
        heading_offset,
        num_columns,
    ):
        self.pdfplumber_config = pdfplumber_config
        self.edit_doc = edit_doc
        self.skip_row_with_merged_cells = skip_row_with_merged_cells
        self.header_row = header_row
        self.conf_stub = conf_stub
        self.log_level = logging.DEBUG if log_level == "debug" else logging.INFO
        self.heading_offset = heading_offset
        self.num_columns = num_columns

        self.conf_dir = Path("conf")

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

    def words_inxyrange(self, words, box):
        xrange, yrange = (box.top.x, box.bot.x), (box.top.y, box.bot.y)
        words = [w for w in words if w.box.in_xrange(xrange)]
        words = [w for w in words if w.box.in_yrange(yrange)]
        return words

    def words_inxyrange2(self, words, box, overlap_percent=80):
        words = [w for w in words if w.shape.overlaps(box, overlap_percent)]
        return words

    def is_skip_row(self, pdf_row):
        # if any of the values are None, means the cells are merged
        if self.skip_row_with_merged_cells:
            return len([c for c in pdf_row.cells if c is None]) > 0
        else:
            return False

    def is_header_row(self, page_idx, table_idx, row_idx):
        if self.header_row == "first_row":
            return row_idx == 0

        elif self.header_row == "first_page_first_row":
            return page_idx == 0 and row_idx == 0

        elif self.header_row == "new_page_first_row":
            return (page_idx == 0 and row_idx == 0) or (page_idx != 0 and table_idx > 0 and row_idx == 0)

        else:
            return False

    def test(self, doc):
        errors = []
        for (page_idx, page) in enumerate(doc.pages):
            for (table_idx, table) in enumerate(page.tables):
                table_path = f"p{page_idx}.t{table_idx}"
                if self.is_header_row(page_idx, table_idx, 0):
                    errors += table.test(table_path)
                else:
                    errors += table.test(table_path, ignore=["TableEmptyHeaderError"])
        self.lgr.debug(f"Data Errors: {len(errors)}")
        [self.lgr.debug(str(error)) for error in errors]
        return errors

    def __call__(self, doc):
        def build_box(pdf_bbox, pdf_size):
            [x0, y0, x1, y1] = pdf_bbox
            (w, h) = pdf_size
            top, bot = Coord(x=x0 / w, y=y0 / h), Coord(x=x1 / w, y=y1 / h)
            return Box(top=top, bot=bot)

        self.add_log_handler(doc)

        doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)
        old_skip_row_with_merged_cells = self.skip_row_with_merged_cells
        self.skip_row_with_merged_cells = doc_config.get("skip_row_with_merged_cells", self.skip_row_with_merged_cells)

        pdf = pdfplumber.open(doc.pdf_path)

        doc.add_extra_page_field("tables", ("list", "docint.table", "Table"))
        doc.add_extra_page_field("heading", ("obj", "docint.region", "Region"))

        for (page_idx, (page, pdf_page)) in enumerate(zip(doc.pages, pdf.pages)):
            pdf_page = pdf_page.dedupe_chars(tolerance=1)
            table_finder = pdf_page.debug_tablefinder(self.pdfplumber_config)

            tables = []
            pdf_size = (pdf_page.width, pdf_page.height)
            for (table_idx, pdf_table) in enumerate(table_finder.tables):
                # table_box = build_box(pdf_table.bbox, pdf_size)
                # table_words = self.words_inxyrange2(page.words, table_box)

                body_rows, header_rows, row_idx = [], [], 0
                for pdf_row in pdf_table.rows:
                    row_box = build_box(pdf_row.bbox, pdf_size)
                    row_words = self.words_inxyrange2(page.words, row_box)

                    cells, cell_texts = [], []
                    for pdf_cell in pdf_row.cells:
                        if pdf_cell is None:
                            continue

                        cell_box = build_box(pdf_cell, pdf_size)
                        cell_words = self.words_inxyrange2(row_words, cell_box)
                        cells.append(Cell.build(cell_words))
                        cell_texts.append(" ".join(w.text for w in cell_words))
                        # print(', '.join(w.text for w in cell_words))

                    row = Row.build(cells)
                    if self.is_skip_row(pdf_row):
                        status = "S"
                    elif self.is_header_row(page_idx, table_idx, row_idx):
                        status = "H"
                        header_rows.append(row)
                    else:
                        status = "B"
                        body_rows.append(row)
                    row_text = ", ".join(cell_texts)
                    self.lgr.debug(f"{page_idx}>{table_idx}:{row_idx} {len(cells)} {status} {row_text}")
                    row_idx += 1 if status != "S" else 0

                tables.append(Table.build(body_rows, header_rows))
            page.tables = tables

            if page_idx == 0:
                offset = self.heading_offset / page.height
                page.heading = page.words_to("above", tables[0], offset)
                heading_str = " ".join([w.text for w in page.heading.words])
                # regSearchInText 'addl[\. ]*s[\.]?p[\.]?' 'dy[\. ]*s[\.]?p[\.]?'
                self.lgr.debug(f"Heading {offset}: {heading_str}")
                # print(f'Heading {offset}: {heading_str}')
        errors = self.test(doc)

        self.lgr.info(f"==Total:{len(errors)} {DataError.error_counts(errors)}")

        self.skip_row_with_merged_cells = old_skip_row_with_merged_cells
        self.remove_log_handler(doc)
        return doc
