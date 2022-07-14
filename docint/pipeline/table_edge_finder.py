import copy
import functools
import logging
import sys
from dataclasses import dataclass
from itertools import chain, groupby
from pathlib import Path
from statistics import mean
from typing import List

from more_itertools import pairwise
from PIL import Image
from pydantic import BaseModel

from ..page import Page
from ..region import DataError
from ..shape import Coord, Edge
from ..util import load_config
from ..vision import Vision


class TableEdges(BaseModel):
    row_edges: List[Edge]
    col_edges: List[Edge]
    errors: List[DataError] = []
    col_img_xs: List[int] = []

    class Config:
        fields = {"col_img_xs": {"exclude": True}}


class MismatchColumnEdges(DataError):
    exp_cols: int
    act_cols: int
    col_img_xs: List[int]


@dataclass
class EdgeFinderPageConfig:
    col_erode_iterations: int
    crop_threshold: int
    skew_threshold: float
    rm_column_atidxs: List[int]
    add_column_atpos: List[int]


@Vision.factory(
    "table_edge_finder",
    default_config={
        "doc_confdir": "conf",
        "pre_edit": True,
        "expected_columns": 4,
        "image_root": ".img",
        "col_erode_iterations": 3,
        "crop_threshold": 75,
        "skew_threshold": 1.0,
    },
)
class TableEdgeFinder:
    def __init__(
        self,
        doc_confdir,
        pre_edit,
        expected_columns,
        image_root,
        col_erode_iterations,
        crop_threshold,
        skew_threshold,
    ):
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.expected_columns = expected_columns
        self.conf_stub = "table_edge_finder"
        self.image_root = Path(image_root)
        self.col_erode_iterations = col_erode_iterations
        self.crop_threshold = crop_threshold
        self.skew_threshold = skew_threshold

        self.xgutter = 0
        self.ygutter = 0
        self.crop_gutter = 0.05
        self.prev_row_ht = None

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

    def get_image_path(self, page):
        page_num = page.page_idx + 1
        angle = getattr(page, "reoriented_angle", 0)
        if angle != 0:
            angle = page.reoriented_angle
            print(f"Page: {page_num} Rotated: {angle}")
            img_filename = Path(f"orig-{page_num:03d}-000-r{angle}.png")
        else:
            img_filename = Path(f"orig-{page_num:03d}-000.png")

        return self.image_root / page.doc.pdf_stem / img_filename

    def find_column_ranges(self, page, conf, xmin=None, ymin=None, ymax=None):
        import cv2
        import numpy as np

        def save_image(cv_img, stub, work_dir=".tmp/"):
            img_file_name = Path(work_dir) / f"{stub}-{page.page.page_idx}.png"
            img_pil = Image.fromarray(cv_img)
            img_pil.save(img_file_name)

        if isinstance(page, Page):
            image_path = self.get_image_path(page)
            img = cv2.imread(str(image_path), 0)
        else:
            page_image = page
            wand_image = page_image.wimage
            img_buffer = np.asarray(bytearray(wand_image.make_blob()), dtype=np.uint8)
            img = cv2.imdecode(img_buffer, cv2.IMREAD_GRAYSCALE)
            # img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # save_image(img, 'orig')

        # thresholding the image to a binary image
        thresh, img_bin = cv2.threshold(
            img, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
        )
        # inverting the image
        img_bin = 255 - img_bin

        # TODO incrase kernel for #205249
        # Length(width) of kernel as 100th of total width
        kernel_len = np.array(img).shape[1] // 100 + 4

        # Defining a vertical kernel to detect all vertical lines of image
        ver_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, kernel_len))

        # A kernel of 2x2
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))

        # Use vertical kernel to detect and save the vertical lines in a jpg
        image_v = cv2.erode(img_bin, ver_kernel, iterations=conf.col_erode_iterations)
        vertical_lines = cv2.dilate(image_v, ver_kernel, iterations=3)

        # save_image(vertical_lines, 'after_morph')

        # Eroding and thesholding the image
        img_vh = vertical_lines
        img_vh2 = cv2.erode(~img_vh, kernel, iterations=2)
        thresh, img_vh2 = cv2.threshold(
            img_vh2, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU
        )

        img_vh2_inv = ~img_vh2

        # blank out the areas outside the table
        height, width = img_vh2_inv.shape
        if ymin is not None:
            img_vh2_inv[:ymin, 0:width] = 0
        if ymax is not None:
            img_vh2_inv[ymax:, 0:width] = 0
        if xmin is not None:
            img_vh2_inv[:height, 0:xmin] = 0

        # identify the ranges for columns (val=1)
        colIdentity = img_vh2_inv.sum(axis=0)
        colIdentity[colIdentity > 0] = 1

        val_ranges = {}
        col_idx = list(range(len(colIdentity)))
        for k, g in groupby(zip(colIdentity, col_idx), key=lambda tup: tup[0]):
            g = list(g)
            val_ranges.setdefault(k, []).append((g[0][1], g[-1][1] + 1))
        # end

        # merge val_ranges
        one_ranges = val_ranges.get(1, [])
        # print(one_ranges)
        if len(one_ranges) > self.expected_columns:
            merge_width = int((width / 800) * 10)

            def merge_ranges(ranges, range):
                if not ranges:
                    return [range]

                last_range = ranges.pop()
                if (range[0] - last_range[1]) < merge_width:
                    ranges.append((last_range[0], range[1]))
                else:
                    ranges.append(last_range)
                    ranges.append(range)
                return ranges

            one_ranges = functools.reduce(merge_ranges, one_ranges, [])
        return one_ranges

    def find_table_edges(self, page, conf):
        if not page.num_markers:
            return []

        # split the markers in to tables
        start_idx, table_markers_list = 0, []
        for idx, marker in enumerate(page.num_markers):
            if marker.num_val == 1 and idx != 0:
                table_markers_list.append(page.num_markers[start_idx:idx])
                start_idx = idx

        table_markers_list.append(page.num_markers[start_idx:])
        table_edges_list = []
        self.lgr.info(f">Page: {page.page_idx}")

        for table_markers in table_markers_list:
            if page.page_idx == 9:
                print("Found it")

            if not table_markers:
                continue

            ymin = table_markers[0].ymin - self.ygutter
            ymax = table_markers[-1].ymin  # does not include last row

            table_words = page.words_in_yrange((ymin, ymax), partial=True)
            xmax = max(w.xmax for w in table_words) + self.xgutter
            xmin = min(m.xmin for m in table_markers) - self.xgutter

            img_xmin = 0  # page.get_image_x_val(xmin)
            img_ymin = page.get_image_y_val(ymin)
            img_ymax = page.get_image_y_val(ymax)

            col_ranges = self.find_column_ranges(
                page, conf, img_xmin, img_ymin, img_ymax
            )
            col_img_xs = [int((x2 + x1) / 2) for (x1, x2) in col_ranges]

            col_xs = [page.get_doc_x_val(img_x) for img_x in col_img_xs]
            # print(col_xs)
            if not col_xs:
                continue

            # FILL ROW EDGES
            xmin = col_xs[0]
            xmax = col_xs[-1]
            row_edges = [
                Edge.build_h(xmin, m.ymin - self.ygutter, xmax, m.ymin - self.ygutter)
                for m in table_markers
            ]
            avg_row_ht = mean(
                (m2.ymin - m1.ymin) for (m1, m2) in pairwise(table_markers)
            )
            ymax += avg_row_ht
            botom_edge = Edge.build_h(xmin, ymax, xmax, ymax)
            row_edges.append(botom_edge)

            col_edges = [Edge.build_v(x, ymin, x, ymax) for x in col_xs]
            table_edges_list.append(
                TableEdges(row_edges=row_edges, col_edges=col_edges)
            )

        # end for
        return table_edges_list

    def find_table_edges2(self, page, conf):
        def split_markers_in_tables(num_markers):
            start_idx, table_markers_list = 0, []
            for idx, marker in enumerate(num_markers):
                if marker.num_val == 1 and idx != 0:
                    table_markers_list.append(num_markers[start_idx:idx])
                    start_idx = idx
            table_markers_list.append(page.num_markers[start_idx:])
            table_markers_list = [t for t in table_markers_list if t]
            return table_markers_list

        def build_row_edge(img_xmin, img_xmax, ymin):
            lt_img_ymin = page_image.get_image_coord(Coord(x=0.0, y=ymin))
            # rt_img_ymin = page_image.get_image_coord(Coord(x=1.0, y=ymin))

            lt_ymin = page_image.get_doc_coord(Coord(x=img_xmin, y=lt_img_ymin.y))
            rt_ymin = page_image.get_doc_coord(Coord(x=col_img_xs[-1], y=lt_img_ymin.y))
            row_edge = Edge.build_h(lt_ymin.x, lt_ymin.y, rt_ymin.x, rt_ymin.y)
            return row_edge

        def build_col_edge(img_xmin, img_xmax, img_x, top_edge, bot_edge):
            len_percent = (img_x - img_xmin) / (img_xmax - img_xmin)
            top_coord = top_edge.get_coord(len_percent)
            bot_coord = bot_edge.get_coord(len_percent)
            return Edge.build_v(top_coord.x, top_coord.y, bot_coord.x, bot_coord.y)

        self.lgr.debug(f"> Page: {page.page_idx}")
        if not page.num_markers:
            return []

        page_image, table_edges_list = page.page_image, []
        table_markers_list = split_markers_in_tables(page.num_markers)

        print(f"> Page: {page.page_idx}")

        # b /Users/mukund/Software/docInt/docint/pipeline/table_edge_finder.py:302
        for row_markers in table_markers_list:
            row_ht = mean((m2.ymin - m1.ymin) for (m1, m2) in pairwise(row_markers))
            ymin = row_markers[0].ymin - self.ygutter
            ymax = row_markers[-1].ymin + (row_ht * 1.1)

            if (ymax - ymin) * 100 < conf.crop_threshold:
                print(f"\tCropping Image {(ymax-ymin)*100} {conf.crop_threshold}")
                top_y, bot_y = ymin - self.crop_gutter, ymax + (self.crop_gutter)
                top_y, bot_y = max(0.0, top_y), min(1.0, bot_y)

                top, bot = Coord(x=0.0, y=top_y), Coord(x=1.0, y=bot_y)
                page_image.crop(top, bot)
            else:
                top, bot = Coord(x=0.0, y=0.0), Coord(x=1.0, y=1.0)

            v_skew_angle = page_image.get_skew_angle("v")
            h_skew_angle = page_image.get_skew_angle("h")
            print(f"\tv_skew_angle: {v_skew_angle} h_skew_angle: {h_skew_angle}")

            if abs(v_skew_angle) > conf.skew_threshold:
                print("\tRotating Image")
                page_image.rotate(v_skew_angle)

            col_ranges = self.find_column_ranges(page_image, conf)
            # print(col_ranges)
            col_img_xs = [int((x2 + x1) / 2) for (x1, x2) in col_ranges]

            if conf.rm_column_atidxs:
                print(f"\t\tRemoving columns: {conf.rm_column_atidxs}")
                col_img_xs = [
                    img_xs
                    for idx, img_xs in enumerate(col_img_xs)
                    if idx not in conf.rm_column_atidxs
                ]

            if conf.add_column_atpos:
                col_img_xs.extend(conf.add_column_atpos)
                col_img_xs.sort()
                print(f"\t\tAdding columns: {conf.add_column_atpos}")

            print(f"> {page.page_idx} Column img_xs[{len(col_img_xs)}]: {col_img_xs}")

            img_xmin, img_xmax = col_img_xs[0], col_img_xs[-1]

            row_edges = [
                build_row_edge(img_xmin, img_xmax, m.ymin) for m in row_markers
            ]
            row_edges.append(build_row_edge(img_xmin, img_xmax, ymax))

            top_edge, bot_edge = row_edges[0], row_edges[-1]
            col_edges = [
                build_col_edge(img_xmin, img_xmax, x, top_edge, bot_edge)
                for x in col_img_xs
            ]

            table_edges = TableEdges(row_edges=row_edges, col_edges=col_edges)
            table_edges_list.append(table_edges)
            page_image.clear_transforms()
        return table_edges_list

    def get_column_edges(self, page_image, crop_coords, conf):
        page_image.clear_transforms()

        if crop_coords:
            top, bot = crop_coords
            page_image.crop(top, bot)

        v_skew_angle = page_image.get_skew_angle("v")

        if abs(v_skew_angle) > conf.skew_threshold:
            self.lgr.debug(f"\tRotating Image v_skew_angle: {v_skew_angle}")
            page_image.rotate(v_skew_angle)

        img_xmax, img_ymax = page_image.curr_size

        col_ranges = self.find_column_ranges(page_image, conf)
        col_img_xs = [int((x2 + x1) / 2) for (x1, x2) in col_ranges]

        if conf.rm_column_atidxs:
            self.lgr.info(f"\t\tRemoving columns: {conf.rm_column_atidxs}")
            col_img_xs = [
                img_xs
                for idx, img_xs in enumerate(col_img_xs)
                if idx not in conf.rm_column_atidxs
            ]

        if conf.add_column_atpos:
            col_img_xs.extend(conf.add_column_atpos)
            col_img_xs.sort()
            self.lgr.info(f"\t\tAdding columns: {conf.add_column_atpos}")

        page_idx = page_image.page.page_idx
        self.lgr.info(
            f"> Page {page_idx} Column img_xs[{len(col_img_xs)}]: {col_img_xs}"
        )

        col_top_img_coords = [Coord(x=img_x, y=0) for img_x in col_img_xs]
        col_bot_img_coords = [Coord(x=img_x, y=img_ymax) for img_x in col_img_xs]

        col_top_doc_coords = [page_image.get_doc_coord(c) for c in col_top_img_coords]
        col_bot_doc_coords = [page_image.get_doc_coord(c) for c in col_bot_img_coords]
        page_image.clear_transforms()

        zip_col_coords = zip(col_top_doc_coords, col_bot_doc_coords)
        col_edges = [Edge.build_v_oncoords(top, bot) for top, bot in zip_col_coords]

        return col_edges, col_img_xs

    def get_row_edges(self, page_image, row_markers, crop_coords, conf):
        page_image.clear_transforms()
        if len(row_markers) > 1:
            row_ht = mean((m2.ymin - m1.ymin) for (m1, m2) in pairwise(row_markers))
        else:
            row_ht = self.prev_row_ht

        if crop_coords:
            top, bot = crop_coords
            page_image.crop(top, bot)

        h_skew_angle = page_image.get_skew_angle("h")

        if abs(h_skew_angle) > conf.skew_threshold:
            self.lgr.debug(f"\tRotating Image h_skew_angle: {h_skew_angle}")
            page_image.rotate(h_skew_angle)

        img_xmax, img_ymax = page_image.curr_size

        m_doc_coords = [Coord(x=m.xmid, y=m.ymin) for m in row_markers]

        last_m = row_markers[-1]
        m_doc_coords.append(Coord(x=last_m.xmid, y=last_m.ymin + (row_ht * 1.1)))

        m_img_coords = [page_image.get_image_coord(c) for c in m_doc_coords]

        row_lt_img_coords = [Coord(x=0, y=m_img.y) for m_img in m_img_coords]
        row_rt_img_coords = [Coord(x=img_xmax, y=m_img.y) for m_img in m_img_coords]

        row_lt_doc_coords = [page_image.get_doc_coord(c) for c in row_lt_img_coords]
        row_rt_doc_coords = [page_image.get_doc_coord(c) for c in row_rt_img_coords]
        page_image.clear_transforms()

        zip_row_coords = zip(row_lt_doc_coords, row_rt_doc_coords)
        row_edges = [Edge.build_h_oncoords(lt, rt) for lt, rt in zip_row_coords]
        self.prev_row_ht = row_ht

        return row_edges

    def find_table_edges3(self, page, conf):
        def split_markers_in_tables(num_markers):
            start_idx, table_markers_list = 0, []
            for idx, marker in enumerate(num_markers):
                if marker.num_val == 1 and idx != 0:
                    table_markers_list.append(num_markers[start_idx:idx])
                    start_idx = idx
            table_markers_list.append(page.num_markers[start_idx:])
            table_markers_list = [t for t in table_markers_list if t]
            return table_markers_list

        self.lgr.debug(f"> Page: {page.page_idx}")
        if not page.num_markers:
            return []

        page_image, table_edges_list = page.page_image, []
        table_markers_list = split_markers_in_tables(page.num_markers)
        for row_markers in table_markers_list:
            if len(row_markers) > 1:
                row_ht = mean((m2.ymin - m1.ymin) for (m1, m2) in pairwise(row_markers))
            else:
                row_ht = self.prev_row_ht
            ymin = row_markers[0].ymin - self.ygutter
            ymax = row_markers[-1].ymin + (row_ht * 1.1)

            # crop the image first
            crop_coords = []
            if (ymax - ymin) * 100 < conf.crop_threshold:
                self.lgr.debug(
                    f"\tCropping Image {(ymax-ymin)*100} {conf.crop_threshold}"
                )
                top_y, bot_y = ymin - self.crop_gutter, ymax + (self.crop_gutter)
                top_y, bot_y = max(0.0, top_y), min(1.0, bot_y)

                top, bot = Coord(x=0.0, y=top_y), Coord(x=1.0, y=bot_y)
                crop_coords.extend([top, bot])
            else:
                top, bot = Coord(x=0.0, y=0.0), Coord(x=1.0, y=1.0)

            col_edges, col_img_xs = self.get_column_edges(page_image, crop_coords, conf)
            row_edges = self.get_row_edges(page_image, row_markers, crop_coords, conf)

            table_edges = TableEdges(
                row_edges=row_edges, col_edges=col_edges, col_img_xs=col_img_xs
            )
            table_edges_list.append(table_edges)
            self.prev_row_ht = row_ht
        return table_edges_list

    def test(self, page, table_edges_list):
        for idx, table_edges in enumerate(table_edges_list):
            act_cols = len(table_edges.col_edges) - 1
            if act_cols != self.expected_columns:
                path = f"pa{page.page_idx}.te{idx}"
                msg = f"Expected {self.expected_columns} Actual: {act_cols}"
                err = MismatchColumnEdges(
                    path=path,
                    msg=msg,
                    exp_cols=self.expected_columns,
                    act_cols=act_cols,
                    col_img_xs=table_edges.col_img_xs,
                )
                table_edges.errors.append(err)
        return list(chain(*[t.errors for t in table_edges_list]))

    def set_page_configs(self, doc, doc_config):
        num_pages = len(doc.pages)
        page_config = EdgeFinderPageConfig(
            col_erode_iterations=doc_config.get(
                "col_erode_iterations", self.col_erode_iterations
            ),
            crop_threshold=self.crop_threshold,
            skew_threshold=self.skew_threshold,
            rm_column_atidxs=[],
            add_column_atpos=[],
        )

        self.page_configs = [copy.copy(page_config) for idx in range(num_pages)]

        file_page_configs = doc_config.get("page_configs", [])
        for file_page_config in file_page_configs:
            page_idx = file_page_config["page_idx"]
            [
                setattr(self.page_configs[page_idx], k, v)
                for (k, v) in file_page_config.items()
                if k != "page_idx"
            ]

    def get_fix_str(self, doc, error):
        page_path, te_path = error.path.split(".")
        page_idx = int(page_path[2:])
        image_path = self.get_image_path(doc.pages[page_idx])
        xs = error.col_img_xs

        html = f"<h1>{doc.pdf_name}:> Page {page_idx} img_xs:[{len(xs)}] {xs}</h1>\n"
        html += f'<img src="{str(image_path)}">'

        yml = f"  - page_idx: {page_idx}\n    add_column_atpos: []\n"
        yml += "    rm_column_atidxs: []\n"
        return (html, yml)

    def write_fixes(self, doc, errors):
        if not errors:
            return

        html_ymls = [self.get_fix_str(doc, e) for e in errors]
        with open("fix.html", "a") as html_file:
            html_file.write("\n\n".join(tup[0] for tup in html_ymls))
            html_file.write("<hr>")

        with open("fix.yml", "a") as yml_file:
            yml_str = "\n".join(tup[1] for tup in html_ymls)
            yml_file.write(f"#F {doc.pdf_name}\n")
            yml_file.write(f"page_configs:\n{yml_str}\n")

    def __call__(self, doc):
        import cv2  # noqa: F401
        import numpy as np  # noqa: F401

        self.add_log_handler(doc)
        self.lgr.info(f"column_finder: {doc.pdf_name}")

        doc_config = load_config(self.doc_confdir, doc.pdf_name, self.conf_stub)
        self.set_page_configs(doc, doc_config)

        doc.add_extra_page_field("table_edges_list", ("list", __name__, "TableEdges"))
        doc.add_extra_page_field("edges", ("list", "docint.shape", "Edge"))

        total_tables, errors = 0, []
        for page, page_config in zip(doc.pages, self.page_configs):
            page.table_edges_list = self.find_table_edges3(page, page_config)
            page.edges = list(chain(*(t.row_edges for t in page.table_edges_list)))
            page.edges += list(chain(*(t.col_edges for t in page.table_edges_list)))
            errors += self.test(page, page.table_edges_list)
            total_tables += len(page.table_edges_list)

        self.lgr.info(
            f"=={doc.pdf_name}.num_marker {total_tables} {DataError.error_counts(errors)}"
        )
        [self.lgr.info(e.msg) for e in errors]

        self.write_fixes(doc, errors)

        self.remove_log_handler(doc)
        return doc
