import functools
import logging
import string
import sys
from pathlib import Path

from more_itertools import pairwise, partition

from ..region import DataError
from ..shape import Box
from ..table import Cell, Row, Table, TableEmptyBodyCellError, TableIncorectSeqError
from ..util import load_config
from ..vision import Vision


@Vision.factory(
    "table_builder_on_edges",
    default_config={
        "doc_confdir": "conf",
        "conf_stub": "table_builder_on_edges",
    },
)
class TableBuilderOnEdges:
    def __init__(
        self,
        doc_confdir,
        conf_stub,
    ):
        self.doc_confdir = doc_confdir
        self.conf_stub = conf_stub

        self.punc_tbl = str.maketrans(string.punctuation, " " * len(string.punctuation))
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

    def test(self, page_idx, table_idx, table):
        def get_num(text):
            try:
                return int(text)
            except Exception as e:  # noqa: F841
                return None

        exp_val, errors = 1, []
        for row_idx, col_idx, cell in table.iter_body_cells():
            cell_text = cell.raw_text().translate(self.punc_tbl).strip()
            path = f"p{page_idx}.ta{table_idx}.ro{row_idx}.co{col_idx}"
            if not cell_text:
                msg = "Emtpy cell"
                errors.append(TableEmptyBodyCellError(path=path, msg=msg, is_none=False))

            if col_idx == 0:
                act_val = get_num(cell_text.strip(" .,"))
                exp_val = act_val if row_idx == 0 and act_val else exp_val
                if not act_val or act_val != exp_val:
                    msg = f"Expected: {exp_val} Actual: {cell_text}"
                    errors.append(TableIncorectSeqError(path=path, msg=msg, exp_val=exp_val, act_val=cell_text))
                    exp_val = act_val if act_val else exp_val + 1
                exp_val += 1
        return errors

    def build_table2(self, page, table_edges, table_idx):
        def in_box(word, box):
            return word.box.get_overlap_percent(box) >= 50

        ymin, ymax = table_edges.row_edges[0].ymin, table_edges.row_edges[-1].ymax
        table_words = page.words_in_yrange((ymin, ymax), partial=True)

        missed_words = []
        remain_table_words, body_rows, page_idx = table_words, [], page.page_idx
        for row_idx, (row1, row2) in enumerate(pairwise(table_edges.row_edges)):
            row_box = Box.build(row1.coords + row2.coords)
            in_row_box = functools.partial(in_box, box=row_box)
            remain_table_words, row_words = partition(in_row_box, remain_table_words + missed_words)
            remain_table_words, row_words = list(remain_table_words), list(row_words)
            self.lgr.debug(f"{page_idx}>{row_idx}")
            self.lgr.debug(f'\t{"|".join(w.text for w in row_words)}')

            remain_row_words, cells, missed_words = list(row_words), [], []
            for col_idx, (col1, col2) in enumerate(pairwise(table_edges.col_edges)):
                # if table_idx == 0 and row_idx == 3 and col_idx == 3:
                #     print('Found It')

                top_lt, top_rt = row1.cross(col1), row1.cross(col2)
                bot_lt, bot_rt = row2.cross(col1), row2.cross(col2)

                xmin, xmax = max(top_lt.x, bot_lt.x), min(top_rt.x, bot_rt.x)
                ymin, ymax = max(top_lt.y, top_rt.y), min(bot_lt.y, bot_rt.y)
                cell_box = Box.build_box([xmin, ymin, xmax, ymax])
                # cell_box = Box.build([top_lt, top_rt, bot_lt, bot_rt])

                in_col_box = functools.partial(in_box, box=cell_box)
                remain_row_words, cell_words = partition(in_col_box, remain_row_words)
                remain_row_words, cell_words = list(remain_row_words), list(cell_words)
                cells.append(Cell.build(cell_words))

                self.lgr.debug(f'\t\t{"|".join(w.text for w in cell_words)}')
            #
            missed_words = remain_row_words

            body_rows.append(Row.build(cells))
            row_text = "|".join(c.raw_text() for c in body_rows[-1].cells)
            self.lgr.debug(f"{page_idx}>{table_idx}:{row_idx} {len(cells)}|{row_text}")
        return Table.build(body_rows)

    # def build_table(self, page, table_edges, table_idx):
    #     def in_box(word, box):
    #         return word.box.get_overlap_percent(box) >= 50

    #     ymin, ymax = table_edges.row_edges[0].ymin, table_edges.row_edges[-1].ymax
    #     table_words = page.words_in_yrange((ymin, ymax), partial=True)

    #     page_idx = page.page_idx
    #     remain_table_words, body_rows = table_words, []

    #     for (row_idx, (row1, row2)) in enumerate(pairwise(table_edges.row_edges)):
    #         print(len(remain_table_words))
    #         row_box = Box.build(row1.coords + row2.coords)
    #         in_row_box = functools.partial(in_box, box=row_box)
    #         remain_table_words, row_words = partition(in_row_box, remain_table_words)

    #         remain_row_words, cells = list(row_words), []
    #         for col_idx, col_box in enumerate(col_boxes):
    #             in_col_box = functools.partial(in_box, box=col_box)
    #             remain_row_words, cell_words = partition(in_col_box, remain_row_words)
    #             cell_words = list(cell_words)
    #             cells.append(Cell(words=cell_words, word_lines=[cell_words]))

    #         body_rows.append(Row.build(cells))
    #         row_text = "|".join(c.raw_text() for c in body_rows[-1].cells)
    #         self.lgr.debug(f"{page_idx}>{table_idx}:{row_idx} {len(cells)}|{row_text}")
    #     return Table.build(body_rows)

    def build_tables(self, page, table_edges_list):
        tables = []
        for table_idx, table_edges in enumerate(table_edges_list):
            table = self.build_table2(page, table_edges, table_idx)
            tables.append(table)
        return tables

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"table_builder_on_edges: {doc.pdf_name}")

        doc.add_extra_page_field("tables", ("list", "docint.table", "Table"))

        doc_config = load_config(self.doc_confdir, doc.pdf_name, self.conf_stub)
        edits = doc_config.get("edits", [])
        if edits:
            print(f"Edited document: {doc.pdf_name}")
            doc.edit(edits)

        total_tables, errors = 0, []
        for page in doc.pages:
            page_idx = page.page_idx
            if page.table_edges_list:
                page.tables = self.build_tables(page, page.table_edges_list)
            else:
                page.tables = []

            total_tables += len(page.tables)

            [errors.extend(self.test(page_idx, table_idx, table)) for table_idx, table in enumerate(page.tables)]

        self.lgr.info(f"=={doc.pdf_name}.table_builder_edges {total_tables} {DataError.error_counts(errors)}")
        [self.lgr.info(str(e)) for e in errors]
        self.remove_log_handler(doc)
        return doc


# /Users/mukund/Software/docInt/docint/pipeline/table_builder_edges.py
