from itertools import chain
from operator import attrgetter
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


class TableMultipleSeqError(DataError):
    pass


class Cell(Para):
    @classmethod
    def build(cls, words):
        word_idxs = [w.word_idx for w in words]
        page_idx = words[0].page_idx if words else None
        word_lines_idxs = [[w.word_idx for w in words]]
        return Cell(
            words=words,
            word_lines=[words],
            word_idxs=word_idxs,
            word_lines_idxs=word_lines_idxs,
            page_idx_=page_idx,
        )

    @classmethod
    def build2(cls, words, page_idx):
        word_idxs = [w.word_idx for w in words]
        word_lines_idxs = [[w.word_idx for w in words]]
        return Cell(
            words=words,
            word_lines=[words],
            word_idxs=word_idxs,
            word_lines_idxs=word_lines_idxs,
            page_idx_=page_idx,
        )

    def text_with_break(self):
        arr_words = self.arranged_words(self.words)
        cell_text = "".join(w.text_with_break(ignore_line_break=True) for w in arr_words)
        return cell_text.strip()

    def split_cell(self):
        pass


class Row(Region):
    cells: List[Cell]
    _ALL_TESTS: List[str] = ["TableMismatchColsError", "TableEmptyCellError"]

    @classmethod
    def build(cls, cells):
        words = [w for cell in cells for w in cell.words]
        word_idxs = [w.word_idx for w in words]
        page_idx = words[0].page_idx if words else None
        return Row(words=words, cells=cells, word_idxs=word_idxs, page_idx_=page_idx)

    @classmethod
    def build2(cls, cells, page_idx):
        words = [w for cell in cells for w in cell.words]
        word_idxs = [w.word_idx for w in words]
        return Row(words=words, cells=cells, word_idxs=word_idxs, page_idx_=page_idx)

    def get_regions(self):
        cells = [c for b in self.body_rows for c in b.cells]
        return [self] + cells

    def remove_word(self, word):
        self.remove_word_ifpresent(word)
        [c.remove_word_ifpresent(word) for c in self.cells]

    def __getitem__(self, index):
        return self.cells[index]

    def test(self, path, num_cols=None, is_header=False):
        errors = []
        if num_cols is not None and len(self.cells) != num_cols:
            msg = f"{path}: expected {num_cols} columns, but actual {len(self.cells)}"
            errors.append(TableMismatchColsError(path=path, msg=msg, name="TableMismatchCols"))

        for idx, cell in enumerate(self.cells):
            if not cell:
                cell_path = f"{path}.c{idx}"
                is_none = True if cell is None else False
                msg = f"{cell_path}: emtpy cell is_none: {is_none}"
                if is_header:
                    errors.append(
                        TableEmptyHeaderCellError(
                            path=cell_path, msg=msg, is_none=is_none, name="TableEmptyHeaderCell"
                        )
                    )
                else:
                    errors.append(
                        TableEmptyBodyCellError(
                            path=cell_path, msg=msg, is_none=is_none, name="TableEmptyBodyCell"
                        )
                    )
        return errors

    def get_html_json(self):
        cell_str = ", ".join(f"{idx}: {c.text}" for (idx, c) in enumerate(self.cells))
        return f"{{{cell_str}}}"

    def get_svg_info(self):
        return {"idxs": {"cells": [[w.word_idx for w in c.words] for c in self.cells]}}

    def delete_cells(self, idxs):
        self.cells = [c for (idx, c) in enumerate(self.cells) if idx not in idxs]

    def get_markdown(self):
        r = "|".join(c.text_with_break() for c in self.cells)
        return f"|{r}|"


class TableEdges(BaseModel):
    row_edges: List[Edge]
    col_edges: List[Edge]
    errors: List[DataError] = []
    col_img_xs: List[int] = []

    class Config:
        fields = {"col_img_xs": {"exclude": True}}

    def add_row_edges(self, ys):
        x1 = min(e.xmin for e in self.row_edges)
        x2 = min(e.xmax for e in self.row_edges)

        self.row_edges += [Edge.build_h(x1, y, x2, y) for y in ys]
        self.row_edges.sort(key=attrgetter("ymin"))

    def add_col_edges(self, xs):
        y1 = min(e.ymin for e in self.col_edges)
        y2 = min(e.ymax for e in self.col_edges)

        self.col_edges += [Edge.build_h(x, y1, x, y2) for x in xs]
        self.col_edges.sort(key=attrgetter("xmin"))

    def rm_row_edges_atidxs(self, rm_idxs):
        rm_idxs = [idx if idx >= 0 else len(self.row_edges) + idx for idx in rm_idxs]
        self.row_edges = [e for (idx, e) in enumerate(self.row_edges) if idx not in rm_idxs]

    def rm_col_edges_atidxs(self, rm_idxs):
        self.col_edges = [e for (idx, e) in enumerate(self.col_edges) if idx not in rm_idxs]


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

        num_cols = len(body_rows[0].cells) if body_rows else 0
        print(f"INSIDE: num_rows: {len(body_rows)} num_cols: {num_cols}")

        return Table(
            words=words,
            body_rows=body_rows,
            header_rows=header_rows,
            word_idxs=word_idxs,
            page_idx_=page_idx,
            title=title,
        )

    @classmethod
    def get_relevant_objects(cls, tables, path, shape):
        path_page_idx, _ = path.split(".", 1)
        path_page_idx = int(path_page_idx[2:])

        relevant_rows = []
        for table in tables:
            if table.page_idx != path_page_idx:
                continue

            for row in table.header_rows + table.body_rows:
                if shape.box.overlaps(row.shape.box, 80):
                    relevant_rows.append(row)
        return relevant_rows

    @property
    def num_columns(self):
        row = self.body_rows[0] if self.body_rows else self.header_rows[0]
        return len(row.cells)

    @property
    def num_rows(self):
        return len(self.body_rows)

    def get_column_cells(self, idx, include_header=True):
        if include_header:
            all_rows = self.header_rows + self.body_rows
        else:
            all_rows = self.body_rows
        return [r[idx] for r in all_rows]

    def delete_columns(self, idxs):
        print("INSIDE: deleting columns")
        idxs = idxs if isinstance(idxs, list) else [idxs]
        for row in self.header_rows + self.body_rows:
            row.delete_cells(idxs)

    @property
    def all_rows(self):
        return self.header_rows + self.body_rows

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
            errors.append(TableEmptyError(path=path, msg=msg, name="TableEmpty"))

        if "TableEmptyHeaderError" in do_tests and not self.header_rows:
            msg = f"{path}: no header rows"
            errors.append(TableEmptyHeaderError(path=path, msg=msg, name="TableEmptyHeader"))

        if "TableEmptyBodyError" in do_tests and not self.body_rows:
            msg = f"{path}: no body rows"
            errors.append(TableEmptyBodyError(path=path, msg=msg, name="TableEmptyBody"))

        en_b, en_h = enumerate(self.body_rows), enumerate(self.header_rows)
        errors += chain(*(r.test(f"{path}.b{idx}") for (idx, r) in en_b))
        errors += chain(*(r.test(f"{path}.h{idx}", is_header=True) for (idx, r) in en_h))
        return errors
