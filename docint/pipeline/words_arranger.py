import copy
import logging
import math
import sys
from pathlib import Path

from ..shape import Box, Poly, doc_to_image, image_to_doc, rotate_image_coord, size_after_rotation
from ..util import load_config
from ..vision import Vision
from ..word_line import words_in_lines


@Vision.factory(
    "words_arranger",
    default_config={
        "rotate_page": False,
        "merge_word_len": 3,
        "num_slots": 1000,
        "newline_height_multiple": 1.0,
        "para_indent": True,
        "is_page": False,
        "conf_stub": "words_arranger",
        "conf_dir": "conf",
    },
)
class WordsArranger:
    def __init__(
        self,
        rotate_page,
        merge_word_len,
        num_slots,
        newline_height_multiple,
        para_indent,
        is_page,
        conf_stub,
        conf_dir,
    ):
        self.rotate_page = rotate_page
        self.merge_word_len = merge_word_len
        self.num_slots = num_slots
        self.newline_height_multiple = newline_height_multiple
        self.para_indent = para_indent
        self.is_page = is_page
        self.conf_stub = conf_stub
        self.conf_dir = conf_dir

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
        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def rotate_words_inpage(self, page):
        def rotate_xy(x, y, angle):
            """https://stackoverflow.com/a/70420150"""
            rad_angle = math.radians(angle)
            abs_sin, abs_cos = abs(math.sin(rad_angle)), abs(math.cos(rad_angle))

            new_x = math.ceil(x * abs_cos) + math.ceil(y * abs_sin)
            new_y = math.ceil(x * abs_sin) + math.ceil(y * abs_cos)
            return new_x, new_y

        # def rotate_coord(c, old_size, new_size, angle):
        #     old_w, old_h = old_size
        #     page_coord = Coord(x=c.x * old_w, y=c.y * old_h)

        #     new_coord = page.page_image.transform_rotate(page_coord, angle, old_size, new_size)
        #     new_w, new_h = new_size
        #     return Coord(x=new_coord.x / new_w, y=new_coord.y / new_h)

        def get_shape_str(shape, size):
            w, h = size
            cs = (f"{c.x * w:.0f}:{c.y*h:.0f}" for c in shape.coords)
            return ", ".join(cs)

        def print_details(old_word, new_word):
            old_shp_str = get_shape_str(old_word.shape_, old_size)
            new_shp_str = get_shape_str(new_word.shape_, new_size)
            print(f"{old_word.path_abbr}:{old_word.text} | {old_shp_str} | {new_shp_str}")

        def rotate2_coord(coord):
            old_coord = doc_to_image(coord, old_size)
            new_coord = rotate_image_coord(old_coord, -angle, old_size, new_size)
            return image_to_doc(new_coord, new_size)

        angle = page.num_marker_angle
        new_words = []
        old_size = page.size
        new_size = size_after_rotation(page.size, -angle)

        print(f"old_size: {old_size} new_size: {new_size}")
        for word in page.words:
            new_coords = [rotate2_coord(c) for c in word.shape_.coords]
            new_word = copy.copy(word)  # this doesn't copy coords
            if isinstance(word.shape_, Poly):
                new_word.shape_ = Poly(coords=new_coords)
            else:
                new_word.shape_ = Box.build(new_coords)
            new_words.append(new_word)
            # print_details(word, new_word)

        new_page = copy.copy(page)
        new_page.words = new_words
        return new_page

    def __call__(self, doc):
        self.add_log_handler(doc)
        doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)
        old_rotate_page = self.rotate_page
        self.rotate_page = doc_config.get("rotate_page", self.rotate_page)

        print(f"INSIDE Rotating {doc_config}")
        if not self.rotate_page:
            self.lgr.info("Not Rotating")
            self.rotate_page = old_rotate_page
            self.remove_log_handler(doc)
            return doc

        doc.add_extra_page_field("arranged_word_lines_idxs", ("noparse", "", ""))

        for page in doc.pages:
            page.arranged_word_idxs = []
            page.arranged_new_line_pos = []
            if self.rotate_page:
                print(f"Rotating page: {page.page_idx}")
                r_page = self.rotate_words_inpage(page)
            else:
                r_page = page

            word_lines = words_in_lines(r_page)

            lines_idxs = [[w.word_idx for w in wl] for wl in word_lines]
            page.arranged_word_lines_idxs = lines_idxs

        self.rotate_page = old_rotate_page
        self.remove_log_handler(doc)
        return doc
