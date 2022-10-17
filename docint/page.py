import copy
import math
from typing import Any, List

from pydantic import BaseModel

# from .doc import Doc
from .region import Region
from .shape import Box, Coord, Edge, Poly, Shape
from .word import BreakType, Word


class Page(BaseModel):
    doc: Any
    page_idx: int
    words: List[Word]
    width_: int
    height_: int

    class Config:
        extra = "allow"
        fields = {"doc": {"exclude": True}}

        json_encoders = {
            Word: lambda w: f"{w.page_idx}-{w.word_idx}",
        }

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return Region.build(self.words[idx], self.page_idx)
        elif isinstance(idx, int):  # should I return a region ?
            if idx >= len(self.words):
                print(f"Unknown idx: {idx}")
            return self.words[idx]
        else:
            raise TypeError("Unknown type {type(idx)} this method can handle")

    # def get_region(self, shape, overlap=100):
    #     assert False
    #     pass

    # def get_text_at(self, direction, word, use_ordered=False):
    #     assert False
    #     if direction not in ("left", "right"):
    #         raise ValueError()
    #     pass

    # def get_ordered_words(self):
    #     assert False
    #     pass
    #     # Should this be outside ???

    # def orient_page(self):
    #     assert False
    #     pass

    @property
    def width(self):
        return self.width_

    @property
    def height(self):
        return self.height_

    @property
    def size(self):
        return (self.width_, self.height_)

    @property
    def text(self):
        return " ".join([w.text for w in self.words])

    @property
    def image_size(self):
        page_image = self.doc.page_images[self.page_idx]
        return (page_image.image_width, page_image.image_height)

    @property
    def text_with_ws(self):
        return " ".join([w.text_with_ws for w in self.words])

    @property
    def shape(self):
        return Box(top=Coord(x=0.0, y=0.0), bot=Coord(x=1.0, y=1.0))

    # TODO fix this, can we move page_image to page, actually to a separte object
    @property
    def page_image(self):
        page_image = self.doc.page_images[self.page_idx]
        return page_image

    def get_image_coord(self, coord, img_size=None):
        def get_scale(img_size):
            assert img_size[0] is None or img_size[1] is None
            if img_size[0]:
                return img_size[0] / self.page_image.image_width
            else:
                return img_size[1] / self.page_image.image_height

        coord = self.page_image.get_image_coord(coord)
        if img_size:
            scale = get_scale(img_size)
            coord.x *= scale
            coord.y *= scale
        return coord

    def get_image_shape(self, shape, img_size=None):
        def conv(page_coords):
            return [self.get_image_coord(c, img_size) for c in page_coords]

        # please make VerticalEdge and HorizontalEdge
        if isinstance(shape, Edge):
            return Edge.from_coords(conv(shape.coords), shape.orientation)
        else:
            return type(shape).from_coords(conv(shape.coords))

    # def get_doc_x_val(self, img_x):
    #     # should operate on coords
    #     #print(f'img_x: {img_x}')
    #     page_image = self.doc.page_images[self.page_idx]
    #     image_box = page_image.image_box

    #     page_x_scale =  (image_box.bot.x - image_box.top.x) /page_image.image_width
    #     page_y_scale =  (image_box.bot.y - image_box.top.y) /page_image.image_height
    #     page_scale = page_x_scale

    #     page_x = img_x * page_scale
    #     #print(f'page_x: {page_x}')

    #     doc_x_val = (page_x + image_box.top.x) / self.width
    #     #print (f'doc_x_val: {doc_x_val}')
    #     return doc_x_val

    # def get_doc_y_val(self, img_y):
    #     page_image = self.doc.page_images[self.page_idx]
    #     image_box = page_image.image_box

    #     page_y_scale =  (image_box.bot.y - image_box.top.y) /page_image.image_height
    #     page_y = img_y * page_y_scale

    #     return (page_y + image_box.top.y) / self.height

    # def get_image_x_val(self, x):
    #     #print(f'x: {x}')
    #     # convert 0.0 - 1.0 coords to page_coords
    #     page_x = int(x * self.width)

    #     #print(f'page_x: {page_x}')

    #     page_image = self.doc.page_images[self.page_idx]
    #     image_box = page_image.image_box

    #     image_x_scale = page_image.image_width / (image_box.bot.x - image_box.top.x)

    #     # convert page_coords to image_coords
    #     image_x_val = int((page_x - image_box.top.x) * image_x_scale)
    #     #print(f'image_x_val: {image_x_val}')
    #     return image_x_val

    # def get_image_y_val(self, y):
    #     # convert 0.0 - 1.0 coords to page_coords
    #     page_y = int(y * self.height)

    #     page_image = self.doc.page_images[self.page_idx]
    #     image_box = page_image.image_box

    #     image_y_scale = page_image.image_height / (image_box.bot.y - image_box.top.y)

    #     # convert page_coords to image_coords
    #     return int((page_y - image_box.top.y) * image_y_scale)

    def words_in_xrange(self, xrange, partial=False):
        return [w for w in self.words if w.box.in_xrange(xrange, partial)]

    def words_in_yrange(self, yrange, partial=False):
        return [w for w in self.words if w.box.in_yrange(yrange, partial)]

    def words_to(self, direction, word, offset=1.0, overlap_percent=1.0, min_height=None):
        if direction not in ("left", "right", "above", "below"):
            raise ValueError(f"Incorrect value of direction {direction}")

        if direction in ("left", "right"):
            if direction == "left":
                left_most = max(0.0, word.xmin - offset)
                xrange = (left_most, word.xmin)
            else:
                right_most = min(1.0, word.xmax + offset)
                xrange = (word.xmax, right_most)

            if min_height and word.box.height < min_height:
                height_inc = (min_height - word.box.height) / 2.0
                yrange = (word.ymin - height_inc, word.ymax + height_inc)
            else:
                yrange = (word.ymin, word.ymax)

            horz_words = self.words_in_yrange(yrange, partial=True)
            # horz_words = self.words_in_xrange(xrange, partial=True)

            horz_box = Shape.build_box_ranges(xrange, yrange)
            horz_words = [w for w in horz_words if w.box.overlaps(horz_box, overlap_percent)]
            return Region.build(horz_words, self.page_idx)
        else:
            xrange = (word.xmin, word.xmax)
            if direction == "above":
                # top_most = max(0.0, word.ymin - offset)
                yrange = (0.0, word.ymin)
            else:
                bot_most = min(1.0, word.ymax + offset)
                yrange = (word.ymax, bot_most)

            vert_words = self.words_in_xrange(xrange, partial=True)

            vert_box = Shape.build_box_ranges(xrange, yrange)
            vert_words = [w for w in vert_words if w.box.overlaps(vert_box, overlap_percent)]
            return Region.build(vert_words, self.page_idx)

    # edit methods
    def add_word(self, text, box):
        word_idx = len(self.words)

        word = Word(
            doc=self.doc,
            page_idx=self.page_idx,
            word_idx=word_idx,
            text_=text,
            break_type=BreakType.Space,
            shape_=box,
        )
        self.words.append(word)

    @property
    def page(self):
        return self

    # TODO add svg also to the page.
    def get_base64_image(self, shape, height=50):
        image_box = shape.box
        return self.page_image.get_base64_image(image_box.top, image_box.bot, "png", height=height)

    # def arrange_words(
    #     self,
    #     *,
    #     rotation_threshold=2,
    #     merge_word_len=3,
    #     newline_height_multiple=1.0,
    #     para_indent=True,
    # ):
    #     h_skew_angle = self.page_image.get_skew_angle("h")

    #     page_words, page_image = self.words, self.page_image
    #     if abs(h_skew_angle) > rotation_threshold:
    #         page_image.clear_transforms()
    #         page_image.rotate(h_skew_angle)

    #         # rota_size = self.page_image.curr_size
    #         rota_words_coords = [
    #             [page_image.get_image_coord(c) for c in w.coords] for w in self.words
    #         ]
    #         page_words = [
    #             build_rota_word(w, rc) for (w, rc) in zip(self.words, rota_words_coords)
    #         ]
    #     # end

    #     word_lines = words_in_lines(
    #         page_words, merge_word_len, newline_height_multiple, para_indent
    #     )

    #     word_idxs = [w.word_idx for wl in word_lines for w in wl]
    #     word_idx_lns = [
    #         (w.word_idx, ln) for (ln, wl) in enumerate(word_lines) for w in wl
    #     ]

    #     ordered_pos_word_idxs = sorted(enumerate(word_idxs), key=lambda tup: tup[1])
    #     self.word_idx_pos = [pos for (pos, idx) in ordered_word_idxs]

    #     self.word_idx_lns = [
    #         ln for (w_idx, ln) in sorted(word_idx_lns, key=lambda tup: tup[1])
    #     ]

    # def reorder_words(self, words):
    #     def word_pos(word):
    #         return self.pos_word_idxs[word.word_idx]

    #     return sorted(words, key=word_pos)

    # def reorder_in_word_lines(self, words):
    #     def line_num(word):
    #         return self.word_idx_lns[word.word_idx]

    #     r_words = self.reorder_words(words)
    #     word_lines = []
    #     for (ln, words) in groupby(r_words, key=line_num):
    #         word_lines.append(list(words))
    #     return word_lines

    @classmethod
    def build_rotated(cls, page, angle):
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

        new_page = copy.copy(page)  # this is purposely a shallow copy

        new_words = []
        old_size = page.size
        new_size = rotate_xy(page.width, page.height, angle)
        for word in page.words:
            new_coords = [rotate_coord(c, old_size, new_size, angle) for c in word.shape_.coords]
            new_word = copy.copy(word)  # this doesn't copy coords
            if isinstance(word.shape_, Poly):
                new_word.shape_ = Poly(coords=new_coords)
            else:
                new_word.shape_ = Box.build(new_coords)
            new_words.append(new_word)
            # print_details(word, new_word)

        new_page.words = new_words
        return new_page
