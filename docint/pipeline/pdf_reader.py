import copy
import math

from .. import pdfwrapper
from ..page import Page
from ..shape import Box, Coord, Poly, Shape
from ..vision import Vision
from ..word import BreakType, Word


def rotate_words_inpage(page):
    def rotate_xy(x, y, angle):
        """https://stackoverflow.com/a/70420150"""
        rad_angle = math.radians(angle)
        abs_sin, abs_cos = abs(math.sin(rad_angle)), abs(math.cos(rad_angle))

        new_x = math.ceil(x * abs_cos) + math.ceil(y * abs_sin)
        new_y = math.ceil(x * abs_sin) + math.ceil(y * abs_cos)
        return new_x, new_y

    def rotate_coord(c, old_size, new_size, angle):
        old_w, old_h = old_size
        page_coord = Coord(x=c.x * old_w, y=c.y * old_h)

        new_coord = page.page_image.transform_rotate(page_coord, angle, old_size, new_size)
        new_w, new_h = new_size
        return Coord(x=new_coord.x / new_w, y=new_coord.y / new_h)

    def get_shape_str(shape, size):
        w, h = size
        cs = (f"{c.x * w:.0f}:{c.y*h:.0f}" for c in shape.coords)
        return ", ".join(cs)

    def print_details(old_word, new_word):
        old_shp_str = get_shape_str(old_word.shape_, old_size)
        new_shp_str = get_shape_str(new_word.shape_, new_size)
        print(f"{old_word.path_abbr}:{old_word.text} | {old_shp_str} | {new_shp_str}")

    angle = 0
    new_words = []
    old_size = page.size
    new_size = rotate_xy(page.width, page.height, -1 * angle)
    for word in page.words:

        new_coords = [rotate_coord(c, old_size, new_size, -1 * angle) for c in word.shape_.coords]
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


@Vision.factory(
    "pdf_reader",
    default_config={
        "x_tol": 1,
        "y_tol": 1,
    },
)
class PDFReader:
    def __init__(self, x_tol, y_tol):
        self.x_tol = x_tol
        self.y_tol = y_tol

    def __call__(self, doc):
        def to_doc_coords(bbox, page):
            x0, y0, x1, y1 = bbox
            coords = [
                x0 / page.width,
                y0 / page.height,
                x1 / page.width,
                y1 / page.height,
            ]
            return coords

        # def to_doc_coords(bbox, page):
        #     x0, y0, x1, y1 = bbox
        #     coords = [
        #         x0 / page.height,
        #         y0 / page.width,
        #         x1 / page.height,
        #         y1 / page.width,
        #     ]
        #     coords[0], coords[1] = coords[1], coords[0]
        #     coords[2], coords[3] = coords[3], coords[2]
        #     return coords

        def build_word(word, word_idx, page):
            doc_bbox = to_doc_coords(word.bounding_box, page)
            box = Shape.build_box(doc_bbox)
            return Word(
                doc=doc,
                page_idx=page_idx,
                word_idx=word_idx,
                text_=word.text,
                break_type=BreakType.Space,
                shape_=box,
            )

        pdf = pdfwrapper.open(doc.pdf_path)
        for page_idx, pdf_page in enumerate(pdf.pages):
            words = [build_word(w, idx, pdf_page) for (idx, w) in enumerate(pdf_page.words)]

            page = Page(
                doc=doc,
                page_idx=page_idx,
                words=words,
                width_=pdf_page.width,
                height_=pdf_page.height,
            )
            # print(page[0].text, page[0].shape)
            doc.pages.append(page)
        return doc
