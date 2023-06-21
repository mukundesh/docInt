import functools
import json
import logging
import string
import sys
from pathlib import Path
from statistics import mean

from more_itertools import pairwise, partition
from pydantic.json import pydantic_encoder

from ..data_error import DataError
from ..shape import Box, Coord, Edge
from ..table import (
    Cell,
    Row,
    Table,
    TableEdges,
    TableEmptyBodyCellError,
    TableIncorectSeqError,
    TableMultipleSeqError,
)
from ..util import load_config
from ..vision import Vision


def build_polygon(coords, page, sort_coords=True):
    from shapely.geometry import MultiPoint, Polygon

    img_coords = [(int(c.x * page.width), int(c.y * page.height)) for c in coords]
    #    if sort_coords:
    # img_coords = sorted(img_coords)
    # img_coords[2], img_coords[3] = img_coords[3], img_coords[2]
    mpt = MultiPoint(img_coords)
    return mpt.convex_hull

    # return Polygon(img_coords)


@Vision.factory(
    "table_builder_on_edges2",
    default_config={
        "doc_confdir": "conf",
        "conf_stub": "table_builder_on_edges",
        "delete_empty_columns": True,
        "heading_offset": 0,
        "add_top_row": True,
        "add_bot_row": True,
    },
)
class TableBuilderOnEdges2:
    def __init__(
        self,
        doc_confdir,
        conf_stub,
        delete_empty_columns,
        heading_offset,
        add_top_row,
        add_bot_row,
    ):
        self.doc_confdir = doc_confdir
        self.conf_stub = conf_stub
        self.delete_empty_columns = delete_empty_columns
        self.output_dir = Path("output")
        self.heading_offset = heading_offset
        self.add_top_row = add_top_row
        self.add_bot_row = add_bot_row

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
                errors.append(
                    TableEmptyBodyCellError(
                        path=path, msg=msg, is_none=False, name="TableEmptyBodyCell"
                    )
                )

            if col_idx == 0:
                act_val = get_num(cell_text.strip(" .,"))
                exp_val = act_val if row_idx == 0 and act_val else exp_val
                if not act_val or act_val != exp_val:
                    msg = f"Expected: {exp_val} Actual: {cell_text}"
                    errors.append(
                        TableIncorectSeqError(
                            path=path,
                            msg=msg,
                            exp_val=exp_val,
                            act_val=cell_text,
                            name="TableIncorectSeq",
                        )
                    )
                    exp_val = act_val if act_val else exp_val + 1
                exp_val += 1

                # Multiple numbers
                if len(cell_text.strip().split()) > 1:
                    msg = f"Multiple nums found: {cell_text}"
                    errors.append(
                        TableMultipleSeqError(
                            path=path,
                            msg=msg,
                            name="TableMultipleSeq",
                        )
                    )
        return errors

    # def build_row(self, table_words, col_edges, row_polygon, page, row_idx):
    #     def in_polygon(word, polygon):
    #         w_polygon = build_polygon(word.shape.coords, word.page)
    #         #print(polygon, polygon.is_valid)
    #         #print(w_polygon, w_polygon.is_valid)
    #         if isinstance(w_polygon, Polygon):
    #             w_area = w_polygon.area
    #             i_area = polygon.intersection(w_polygon).area
    #             return i_area/w_area > 0.5
    #         else:
    #             w_length = w_polygon.length
    #             i_line = polygon.intersection(w_polygon)
    #             return i_line.length/w_length > 0.5

    #     in_row_polygon = functools.partial(in_polygon, polygon=row_polygon)
    #     remain_table_words, row_words = partition(in_row_polygon, table_words)
    #     remain_table_words, row_words = list(remain_table_words), list(row_words)
    #     self.lgr.debug(f"{page.page_idx}>{row_idx} # row_words: {len(row_words)}")
    #     self.lgr.debug(f'\t{"|".join(w.text for w in row_words)}')

    #     remain_row_words, cells = list(row_words), []
    #     for col_idx, (col1, col2) in enumerate(pairwise(col_edges)):
    #         top_lt, top_rt = row1.cross(col1), row1.cross(col2)
    #         bot_lt, bot_rt = row2.cross(col1), row2.cross(col2)

    #         cell_polygon = build_polygon([top_lt, top_rt, bot_lt, bot_rt], page)
    #         #print(len(remain_row_words))

    #         in_col_polygon = functools.partial(in_polygon, polygon=cell_polygon)
    #         remain_row_words, cell_words = partition(in_col_polygon, remain_row_words)
    #         remain_row_words, cell_words = list(remain_row_words), list(cell_words)
    #         cells.append(Cell.build(cell_words))

    #         self.lgr.debug(f'\t\t{"|".join(w.text for w in cell_words)}')

    #     remain_words = remain_table_words + remain_row_words
    #     row = Row.build(cells)
    #     return row, remain_words

    def build_table(self, page, table_edges, table_idx):
        from shapely.geometry import MultiPoint, Polygon

        def in_polygon(word, polygon):
            w_polygon = build_polygon(word.shape.coords, word.page)
            # print(polygon, polygon.is_valid)
            # print(w_polygon, w_polygon.is_valid)
            if isinstance(w_polygon, Polygon):
                w_area = w_polygon.area
                i_area = polygon.intersection(w_polygon).area
                return i_area / w_area > 0.5
            else:
                w_line = w_polygon  # word shape is a line
                i_line = polygon.intersection(w_line)
                return i_line.length / w_line.length > 0.5 if w_line.length else True

        def get_col_gap(loc):
            if loc == "top":
                row = table_edges.row_edges[0]
                col_gap = max(row.cross(c).y - c.ymin for c in table_edges.col_edges)
            else:
                assert loc == "bot"
                row = table_edges.row_edges[-1]
                col_gap = max(c.ymax - row.cross(c).y for c in table_edges.col_edges)
            return col_gap

        def is_header(row):
            cell_text = row[0].text.lower()
            row_text = "|".join(c.raw_text() for c in row.cells)
            if cell_text.isascii() and (
                ("s." in cell_text) or ("no." in cell_text) or ("sno" in cell_text)
            ):
                print(f"### {cell_text} True|{row_text}")
                return True

            header_str = "क्र|सं|क.|क ०|कम|कृ0स०|क .|क्र.स.|कृ ० स ०|क स ०|क्रस|वा . स ."

            # if (not cell_text.isascii()) and (('क्र' in cell_text) or ('सं' in cell_text) or ('क.' in cell_text) or ('क ०' in cell_text)):
            if (not cell_text.isascii()) and any(h in cell_text for h in header_str.split("|")):
                print(f"### {cell_text} True |{row_text}")
                return True

            print(f"### >{cell_text}< False")
            return False

        row_edges, col_edges = table_edges.row_edges, table_edges.col_edges
        if len(row_edges) < 2:
            return None

        print(f"Num Rows: {len(row_edges) - 1} Num Cols: {len(col_edges) - 1}")

        avg_row_ht = mean((r2.ymin - r1.ymin for (r1, r2) in pairwise(row_edges)))
        c_ymin, c_ymax = min(c.ymin for c in col_edges), max(c.ymax for c in col_edges)

        if (get_col_gap("top") > (avg_row_ht * 0.6)) and self.add_top_row:
            top_row_edge = Edge.build_h_oncoords(Coord(x=0.0, y=c_ymin), Coord(x=1.0, y=c_ymin))
            row_edges = [top_row_edge] + row_edges
            print("*** Adding top row")

        if get_col_gap("bot") > (avg_row_ht * 0.6) and self.add_bot_row:
            bot_row_edge = Edge.build_h_oncoords(Coord(x=0.0, y=c_ymax), Coord(x=1.0, y=c_ymax))
            row_edges.append(bot_row_edge)
            print("*** Adding bot row")

        ymin, ymax = row_edges[0].ymin, row_edges[-1].ymax
        table_words = page.words_in_yrange((ymin, ymax), partial=True)

        remain_table_words, body_rows, header_rows, page_idx = table_words, [], [], page.page_idx
        for row_idx, (row1, row2) in enumerate(pairwise(row_edges)):
            row_polygon = build_polygon(row1.coords + row2.coords, page, sort_coords=True)

            in_row_polygon = functools.partial(in_polygon, polygon=row_polygon)

            remain_table_words, row_words = partition(in_row_polygon, remain_table_words)
            remain_table_words, row_words = list(remain_table_words), list(row_words)
            self.lgr.debug(f"{page_idx}>{row_idx} # row_words: {len(row_words)}")
            self.lgr.debug(f'\t{"|".join(w.text for w in row_words)}')

            remain_row_words, cells = list(row_words), []
            for col_idx, (col1, col2) in enumerate(pairwise(table_edges.col_edges)):
                # if table_idx == 0 and row_idx == 3 and col_idx == 3:
                #     print('Found It')

                top_lt, top_rt = row1.cross(col1), row1.cross(col2)
                bot_lt, bot_rt = row2.cross(col1), row2.cross(col2)

                cell_polygon = build_polygon([top_lt, top_rt, bot_lt, bot_rt], page)
                # print(len(remain_row_words))

                in_col_polygon = functools.partial(in_polygon, polygon=cell_polygon)
                remain_row_words, cell_words = partition(in_col_polygon, remain_row_words)
                remain_row_words, cell_words = list(remain_row_words), list(cell_words)

                cells.append(Cell.build2(cell_words, page_idx))
                self.lgr.debug(f'\t\t{"|".join(w.text for w in cell_words)}')

            remain_table_words += remain_row_words
            row = Row.build2(cells, page_idx)
            if len([w for w in row.words if w.text]) < 3:
                remain_row_words += row.words  # CHECK this..
                continue

            if (len(header_rows) + len(body_rows)) == 0 and is_header(row):
                header_rows.append(row)
            else:
                body_rows.append(row)

            row_text = "|".join(c.raw_text() for c in row.cells)
            self.lgr.debug(f"{page_idx}>{table_idx}:{row_idx} {len(cells)}|{row_text}")

        table = Table.build(body_rows, header_rows=header_rows)

        # Remove empty column
        num_rows = len(body_rows)
        if self.delete_empty_columns:
            empty_idxs = []
            for idx in range(len(col_edges) - 1):
                num_words = len([c for c in table.get_column_cells(idx) for w in c.words if w.text])
                # num_col_words = sum(len(c.words) for c in table.get_column_cells(idx))
                if (num_rows > 2) and num_words <= 1:  # TODO
                    empty_idxs.append(idx)
            print(f"DELETING COLUMNS: {empty_idxs}")
            table.delete_columns(empty_idxs)
            table_edges.rm_col_edges_atidxs(empty_idxs)

        if page_idx == 0 and self.heading_offset:
            offset = self.heading_offset / page.height
            page.heading = page.words_to("above", table, offset)
            heading_str = " ".join([w.text for w in page.heading.words])
            # regSearchInText 'addl[\. ]*s[\.]?p[\.]?' 'dy[\. ]*s[\.]?p[\.]?'
            self.lgr.debug(f"Heading {offset}: {heading_str}")
            # print(f'Heading {offset}: {heading_str}')

        return table

    def build_table2(self, page, table_edges, table_idx):
        from shapely.geometry import MultiPoint, Polygon

        def in_polygon(word, polygon):
            w_polygon = build_polygon(word.shape.coords, word.page)
            # print(polygon, polygon.is_valid)
            # print(w_polygon, w_polygon.is_valid)
            if isinstance(w_polygon, Polygon):
                w_area = w_polygon.area
                i_area = polygon.intersection(w_polygon).area
                return i_area / w_area > 0.5
            else:
                w_length = w_polygon.length
                i_line = polygon.intersection(w_polygon)
                return i_line.length / w_length > 0.5

        # table_words is taken from ymin & ymax of rows.
        ymin, ymax = table_edges.row_edges[0].ymin, table_edges.row_edges[-1].ymax
        table_words = page.words_in_yrange((ymin, ymax), partial=True)

        missed_words = []
        remain_table_words, body_rows, page_idx = table_words, [], page.page_idx
        for row_idx, (row1, row2) in enumerate(pairwise(table_edges.row_edges)):
            row_polygon = build_polygon(row1.coords + row2.coords, page, sort_coords=True)

            in_row_polygon = functools.partial(in_polygon, polygon=row_polygon)

            remain_table_words, row_words = partition(
                in_row_polygon, remain_table_words + missed_words
            )
            remain_table_words, row_words = list(remain_table_words), list(row_words)
            self.lgr.debug(f"{page_idx}>{row_idx} # row_words: {len(row_words)}")
            self.lgr.debug(f'\t{"|".join(w.text for w in row_words)}')

            remain_row_words, cells, missed_words = list(row_words), [], []
            for col_idx, (col1, col2) in enumerate(pairwise(table_edges.col_edges)):
                # if table_idx == 0 and row_idx == 3 and col_idx == 3:
                #     print('Found It')

                top_lt, top_rt = row1.cross(col1), row1.cross(col2)
                bot_lt, bot_rt = row2.cross(col1), row2.cross(col2)

                cell_polygon = build_polygon([top_lt, top_rt, bot_lt, bot_rt], page)
                # print(len(remain_row_words))

                in_col_polygon = functools.partial(in_polygon, polygon=cell_polygon)
                remain_row_words, cell_words = partition(in_col_polygon, remain_row_words)
                remain_row_words, cell_words = list(remain_row_words), list(cell_words)
                cells.append(Cell.build(cell_words))

                self.lgr.debug(f'\t\t{"|".join(w.text for w in cell_words)}')
            #
            missed_words = remain_row_words

            body_rows.append(Row.build2(cells, page_idx))
            row_text = "|".join(c.raw_text() for c in body_rows[-1].cells)
            self.lgr.debug(f"{page_idx}>{table_idx}:{row_idx} {len(cells)}|{row_text}")

        return Table.build(body_rows)

    def process_table_edges(self, doc):
        edges_stub = "table_edge_finder"
        json_path = self.output_dir / f"{doc.pdf_name}.{edges_stub}.json"

        if doc.has_page_extract("table_edges_list"):
            table_edges_infos = [p.table_edges_list for p in doc.pages]
            json_path.write_text(
                json.dumps({"table_edges_infos": table_edges_infos}, default=pydantic_encoder)
            )
        else:
            doc.add_extra_page_field("table_edges_list", ("list", __name__, "TableEdges"))
            if not any(page for page in doc.pages if page.table_boxes):
                for page in doc.pages:
                    page.table_edges_list = []
            else:
                assert json_path.exists(), f"edges files is not present {json_path}"
                json_dict = json.loads(json_path.read_text())
                for (page, jd_table_edges_list) in zip(doc.pages, json_dict["table_edges_infos"]):
                    page.table_edges_list = [TableEdges(**d) for d in jd_table_edges_list]

    def build_tables(self, page, table_edges_list):
        tables = []
        for table_idx, table_edges in enumerate(table_edges_list):
            table = self.build_table(page, table_edges, table_idx)
            if table:
                tables.append(table)
            else:
                print(f"Empty table: {page.page_idx} {table_idx}")
        return tables

    def __call__(self, doc):
        from shapely.geometry import MultiPoint, Polygon

        self.add_log_handler(doc)
        self.lgr.info(f"table_builder_on_edges: {doc.pdf_name}")

        self.process_table_edges(doc)

        doc.add_extra_page_field("tables", ("list", "docint.table", "Table"))
        doc.add_extra_page_field("heading", ("obj", "docint.region", "Region"))

        json_path = self.output_dir / f"{doc.pdf_name}.{self.conf_stub}.json"
        # if json_path.exists():
        #     json_dict = json.loads(json_path.read_text())
        #     for (page, jd_tables) in zip(doc.pages, json_dict['table_infos']):
        #         page.tables = [Table(**d) for d in jd_tables]

        #     self.remove_log_handler(doc)
        #     return doc

        doc_config = load_config(self.doc_confdir, doc.pdf_name, self.conf_stub)
        edits = doc_config.get("edits", [])
        if edits:
            print(f"Edited document: {doc.pdf_name}")
            doc.edit(edits)

        old_delete_empty_columns = self.delete_empty_columns
        self.delete_empty_columns = doc_config.get(
            "delete_empty_columns", self.delete_empty_columns
        )
        old_add_top_row, old_add_bot_row = self.add_top_row, self.add_bot_row
        self.add_top_row = doc_config.get("add_top_row", self.add_top_row)
        self.add_bot_row = doc_config.get("add_top_row", self.add_bot_row)

        table_configs = doc_config.get("table_configs", [])
        for table_config in table_configs:
            page_idx, table_idx = table_config["page_idx"], table_config["table_idx"]
            table_edges = doc[page_idx].table_edges_list[table_idx]

            rm_idxs = table_config.get("rm_column_atidxs", [])
            table_edges.rm_col_edges_atidxs(rm_idxs)

            rm_idxs = table_config.get("rm_row_atidxs", [])
            table_edges.rm_row_edges_atidxs(rm_idxs)

            xs = table_config.get("add_column_atpos", [])
            xs = [x / doc[page_idx].page_image.image_width for x in xs]
            table_edges.add_col_edges(xs)

            ys = table_config.get("add_row_atpos", [])
            ys = [y / doc[page_idx].page_image.image_height for y in ys]
            table_edges.add_row_edges(ys)

            idxs = table_config.get("add_row_atwordidxs", [])
            idxs_ys = [doc[page_idx].words[idx].ymin for idx in idxs]
            table_edges.add_row_edges(idxs_ys)

        total_tables, errors = 0, []
        for page in doc.pages:
            page_idx = page.page_idx
            if page.table_edges_list:
                page.tables = self.build_tables(page, page.table_edges_list)
            else:
                page.tables = []

            total_tables += len(page.tables)

            [
                errors.extend(self.test(page_idx, table_idx, table))
                for table_idx, table in enumerate(page.tables)
            ]

        self.lgr.info(
            f"=={doc.pdf_name}.table_builder_edges {total_tables} {DataError.error_counts(errors)}"
        )
        [self.lgr.info(str(e)) for e in errors]

        table_infos = [p.tables for p in doc.pages]
        json_path.write_text(json.dumps({"table_infos": table_infos}, default=pydantic_encoder))

        self.delete_empty_columns = old_delete_empty_columns

        self.add_top_row, self.add_bot_row = old_add_top_row, old_add_bot_row

        self.remove_log_handler(doc)
        return doc


# /Users/mukund/Software/docInt/docint/pipeline/table_builder_edges.py
"""
        def build_border_row(loc):
            c_lt, c_rt = table_edges.col_edges[0], table_edges.col_edges[-1]
            int_lt, int_rt = r.cross(c_lt), r.cross(c_rt)
            ext_lt, ext_rt = c_lt.coord1, c_rt.coord1 if loc == 'top' else c_lt.coord2, c_rt.coord2

            coords = [int_lt, int_rt, ext_lt, ext_rt]
            ymin, ymax = min(c.y for c in coords), max(c.y for c in coords)

            border_words = page.words_in_yrange((ymin, ymax), partial=True)
            row_polygon = build_polygon(coords)
            row, remain_words = self.build_row(table_words,row_polygon, page, -1)
            return row

"""
