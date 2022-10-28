from itertools import chain
from typing import List

from pydantic import BaseModel

from .data_error import DataError
from .para import Para
from .region import Region
from .shape import Edge


class TableEmptyError(DataError):
    pass


class TableEmptyHeaderError(DataError):
    pass


class TableEmptyBodyError(DataError):
    pass


class TableMismatchColsError(DataError):
    pass


class TableEmptyBodyCellError(DataError):
    is_none: bool


class TableEmptyHeaderCellError(DataError):
    is_none: bool


class TableIncorectSeqError(DataError):
    exp_val: int
    act_val: str


class Cell(Para):
    @classmethod
    def build(cls, words):
        word_idxs = [w.word_idx for w in words]
        page_idx = words[0].page_idx if words else None
        return Cell(words=words, word_lines=[words], word_idxs=word_idxs, page_idx_=page_idx)


class Row(Region):
    cells: List[Cell]
    _ALL_TESTS: List[str] = ["TableMismatchColsError", "TableEmptyCellError"]

    @classmethod
    def build(cls, cells):
        words = [w for cell in cells for w in cell.words]
        word_idxs = [w.word_idx for w in words]
        page_idx = words[0].page_idx if words else None
        return Row(words=words, cells=cells, word_idxs=word_idxs, page_idx_=page_idx)

    def get_regions(self):
        cells = [c for b in self.body_rows for c in b.cells]
        return [self] + cells

    def remove_word(self, word):
        self.remove_word_ifpresent(word)
        [c.remove_word_ifpresent(word) for c in self.cells]

    def test(self, path, num_cols=None, is_header=False):
        errors = []
        if num_cols is not None and len(self.cells) != num_cols:
            msg = f"{path}: expected {num_cols} columns, but actual {len(self.cells)}"
            errors.append(TableMismatchColsError(path=path, msg=msg))

        for (idx, cell) in enumerate(self.cells):
            if not cell:
                cell_path = f"{path}.c{idx}"
                is_none = True if cell is None else False
                msg = f"{cell_path}: emtpy cell is_none: {is_none}"
                if is_header:
                    errors.append(TableEmptyHeaderCellError(path=cell_path, msg=msg, is_none=is_none))
                else:
                    errors.append(TableEmptyBodyCellError(path=cell_path, msg=msg, is_none=is_none))
        return errors


class TableEdges(BaseModel):
    row_edges: List[Edge]
    col_edges: List[Edge]
    errors: List[DataError] = []
    col_img_xs: List[int] = []

    class Config:
        fields = {"col_img_xs": {"exclude": True}}


class Table(Region):
    header_rows: List[Row]
    body_rows: List[Row]
    title: Region = None

    @classmethod
    def build(cls, body_rows, header_rows=[], title=None):
        words = [w for row in body_rows for w in row.words]
        words += [w for row in header_rows for w in row.words]
        word_idxs = [w.word_idx for w in words]
        page_idx = words[0].page_idx if words else None
        return Table(
            words=words,
            body_rows=body_rows,
            header_rows=header_rows,
            word_idxs=word_idxs,
            page_idx_=page_idx,
            title=title,
        )

    def get_regions(self):
        all_rows = self.body_rows + self.header_rows
        cells = [c for b in all_rows for c in b.cells]
        title = [] if not self.title else [self.title]
        return [self] + all_rows + cells + title

    def iter_body_cells(self):
        for row_idx, row in enumerate(self.body_rows):
            for col_idx, cell in enumerate(row.cells):
                yield row_idx, col_idx, cell

    def test(self, path, ignore=[]):
        errors = []
        all_tests = ["TableEmptyError", "TableEmptyBodyError", "TableEmptyHeaderError"]
        do_tests = [t for t in all_tests if t not in ignore]

        if "TableEmptyError" in do_tests and not self.header_rows and not self.body_rows:  # noqa: W503  # noqa: W503
            msg = f"{path}: Both header and body rows are empty"
            errors.append(TableEmptyError(path=path, msg=msg))

        if "TableEmptyHeaderError" in do_tests and not self.header_rows:
            msg = f"{path}: no header rows"
            errors.append(TableEmptyHeaderError(path=path, msg=msg))

        if "TableEmptyBodyError" in do_tests and not self.body_rows:
            msg = f"{path}: no body rows"
            errors.append(TableEmptyBodyError(path=path, msg=msg))

        en_b, en_h = enumerate(self.body_rows), enumerate(self.header_rows)
        errors += chain(*(r.test(f"{path}.b{idx}") for (idx, r) in en_b))
        errors += chain(*(r.test(f"{path}.h{idx}", is_header=True) for (idx, r) in en_h))
        return errors
