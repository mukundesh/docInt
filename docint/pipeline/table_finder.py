from typing import List
import logging
import itertools as it

from ..vision import Vision
from ..region import Region
from ..util import load_config

class Cell(Region):
    pass

class BodyRow(Region):
    cells: List[Cell]

    @classmethod
    def build(cls, cells):
        words = [w for cell in cells for w in cell.words]
        return BodyRow(words=words, cells=cells)


class Table(Region):
    body_rows: List[BodyRow]

    @classmethod    
    def build(cls, body_rows):
        words = [w for row in body_rows for w in row.words]
        return Table(words=words, body_rows=body_rows)


@Vision.factory(
    "table_finder",
    default_config={
        "doc_confdir": "conf",
        "pre_edit": True,
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
        pre_edit,
        num_slots,
        x_range,
        sent_delim,
        table_header,
    ):
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.sent_delim = sent_delim
        self.table_header = table_header
        self.num_slots = num_slots
        self.x_range = x_range

        s, e = int(x_range[0] * num_slots), int(x_range[1] * num_slots)
        self.x_range_slice = slice(s, e)

        self.logger = logging.getLogger(__name__ + ".FindNumMarker")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(logging.StreamHandler())

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
            gb = it.groupby(enum_slots, key=lambda tup: tup[1] == 0)

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

                lt_cell, rt_cell = Cell(words=lt_words), Cell(words=rt_words)
                #print(f"{list_item.marker.text}|{lt_cell.text}|{rt_cell.text}")

                body_rows.append(BodyRow.build([lt_cell, rt_cell]))
        return Table.build(body_rows)

    def __call__(self, doc):
        self.logger.info(f"processing document: {doc.pdf_name}")
        doc_config = load_config(self.doc_confdir, doc.pdf_name, "listfinder")
        for page in doc.pages:
            if page.list_items:
                page.table = self.find_inpage(page.list_items)
            else:
                page.table = None
        return doc
