import sys
from pathlib import Path
from typing import List
import logging
from itertools import groupby, chain

from pydantic import BaseModel

from ..vision import Vision
from ..region import Region
from ..table import Table, Row, Cell
from ..util import load_config



@Vision.factory(
    "table_finder",
    default_config={
        "doc_confdir": "conf",
        "conf_stub": "table",
        "num_slots": 1000,
        "x_range": [0.3, 0.6],
        "sent_delim": ".;",
        "table_header": True,
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
        table_header,
    ):
        self.doc_confdir = doc_confdir
        self.conf_stub = conf_stub
        self.sent_delim = sent_delim
        self.table_header = table_header
        self.num_slots = num_slots
        self.x_range = x_range

        s, e = int(x_range[0] * num_slots), int(x_range[1] * num_slots)
        self.x_range_slice = slice(s, e)


        self.lgr = logging.getLogger(f'docint.pipeline.{self.conf_stub}')
        self.lgr.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)
        self.file_handler = None

    def add_log_handler(self, doc):
        handler_name = f'{doc.pdf_name}.{self.conf_stub}.log'
        log_path = Path('logs') / handler_name
        self.file_handler = logging.FileHandler(log_path, mode='w')
        self.lgr.info(f'adding handler {log_path}')

        self.file_handler.setLevel(logging.DEBUG)        
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def find_inpage(self, list_items):
        def fill_slots(slots, word):
            min_sidx, max_sidx = int(word.xmin * len(slots)), int(word.xmax * len(slots))
            max_sidx = min(max_sidx, len(slots) - 1)
            for sidx in range(min_sidx, max_sidx + 1):
                slots[sidx] += 1

        def split_words(words, x_range):
            lt_range, rt_range = (0.0, x_range[0]), (x_range[1], 1.0)
            lt_words = [w for w in words if w.box.in_xrange(lt_range, partial=True)]
            rt_words = [w for w in words if w.box.in_xrange(rt_range, partial=True)]
            return lt_words, rt_words

        num_slots = self.num_slots
        body_rows = []
        for idx, list_item in enumerate(list_items):
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
                print("No empty range found, {list_item}")
            else:
                empty_range = max(empty_ranges, key=lambda r: r[1] - r[0])
                empty_range = ((empty_range[0] - 5)/ len(slots), (empty_range[1] +5)/ len(slots))
                lt_words, rt_words = split_words(list_item.words, empty_range)

                lt_cell, rt_cell = Cell(words=lt_words, word_lines=[lt_words]), Cell(words=rt_words, word_lines=[rt_words])
                marker_cell = Cell(words=list_item.marker.words)

                self.lgr.info(f"{list_item.marker.raw_text()}|{lt_cell.raw_text()}|{rt_cell.raw_text()}")

                body_rows.append(Row.build([marker_cell, lt_cell, rt_cell]))
        return Table.build(body_rows)

    def __call__(self, doc):
        self.add_log_handler(doc)                        
        self.lgr.info(f"table_finder: {doc.pdf_name}")

        doc.add_extra_page_field('tables', ('list', 'docint.pipeline.table_finder', 'Table'))
        doc.add_extra_page_field('heading', ('obj', 'docint.region', 'Region'))              

        for page in doc.pages:
            if page.list_items:
                table = self.find_inpage(page.list_items)
                page.tables = [ table]
            else:
                page.tables = []

        self.remove_log_handler(doc)                
        return doc

#/Users/mukund/Software/docInt/docint/pipeline/table_finder.py
