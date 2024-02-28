import copy
from typing import Any, List

from pydantic import BaseModel

from .page_image import PageImage

# from .doc import Doc
from .region import Region
from .shape import (
    Box,
    Coord,
    Edge,
    Poly,
    Shape,
    doc_to_image,
    image_to_doc,
    rotate_image_coord,
    size_after_rotation,
)
from .word import BreakType, Word


class Page(BaseModel):
    doc: Any
    page_idx: int
    words: List[Word]
    width_: int
    height_: int
    page_image: PageImage = None

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

    @classmethod
    def from_page(cls, page, words):
        return Page(
            doc=page.doc,
            page_idx=page.page_idx,
            words=words,
            width_=page.width_,
            height_=page.height_,
        )

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
    def shape(self):
        return Box(top=Coord(x=0.0, y=0.0), bot=Coord(x=1.0, y=1.0))

    @property
    def text(self):
        return " ".join([w.text for w in self.words])

    # @property
    # def page_image(self):
    #     if hasattr(self, page_image):
    #         return self.page_image
    #     else:
    #         raise ValueError('page object does not have page_image')

    @property
    def image_size(self):  # TODO change this to page_image_size
        return self.page_image.size

    @property
    def path_abbr(self):
        return f"pa{self.page_idx}"

    @property
    def text_with_ws(self):
        return " ".join([w.text_with_ws for w in self.words])

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

    ## TODO rename this to get_shape_in_page_image
    def get_image_shape(self, shape, img_size=None):
        def conv(page_coords):
            return [self.get_image_coord(c, img_size) for c in page_coords]

        # please make VerticalEdge and HorizontalEdge
        if isinstance(shape, Edge):
            return Edge.from_coords(conv(shape.coords), shape.orientation)
        else:
            return type(shape).from_coords(conv(shape.coords))

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

    # TODO add svg also to the page.
    @classmethod
    def get_base64_image_from_pil(self, pil_image, shape, height=50):
        image_box = shape.box
        img_w, img_h = pil_image.size

        img_x1, img_y1 = int(image_box.top.x * img_w), int(image_box.top.y * img_h)
        img_x2, img_y2 = int(image_box.bot.x * img_w), int(image_box.bot.y * img_h)
        return pil_image.crop((img_x1, img_y1, img_x2, img_y2))

    @classmethod
    def build_rotated(cls, page, angle):
        def rotate_coord(coord):
            old_coord = doc_to_image(coord, old_size)
            new_coord = rotate_image_coord(old_coord, -angle, old_size, new_size)
            return image_to_doc(new_coord, new_size)

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
        new_size = size_after_rotation(page.size, -angle)
        for word in page.words:
            new_coords = [rotate_coord(c) for c in word.shape_.coords]
            new_word = copy.copy(word)  # this doesn't copy coords
            if isinstance(word.shape_, Poly):
                new_word.shape_ = Poly(coords=new_coords)
            else:
                new_word.shape_ = Box.build(new_coords)
            new_words.append(new_word)
            # print_details(word, new_word)

        new_page.words = new_words
        return new_page

    @classmethod
    def build_rotated2(cls, page, angle):
        def rotate_coord(coord):
            old_coord = doc_to_image(coord, old_size)
            new_coord = rotate_image_coord(old_coord, -angle, old_size, new_size)
            return image_to_doc(new_coord, new_size)

        def get_shape_str(shape, size):
            w, h = size
            cs = (f"{c.x * w:.0f}:{c.y*h:.0f}" for c in shape.coords)
            return ", ".join(cs)

        def print_details(old_word, new_word):
            old_shp_str = get_shape_str(old_word.shape_, old_size)
            new_shp_str = get_shape_str(new_word.shape_, new_size)
            print(f"{old_word.path_abbr}:{old_word.text} | {old_shp_str} | {new_shp_str}")

        new_words = []
        old_size = page.size
        new_size = size_after_rotation(page.size, -angle)
        for word in page.words:
            new_coords = [rotate_coord(c) for c in word.shape_.coords]
            if isinstance(word.shape_, Poly):
                new_shape = Poly(coords=new_coords)
            else:
                new_shape = Box.build(new_coords)
            new_words.append(Word.from_word(word, new_shape))

        new_page = Page.from_page(page, new_words)
        return new_page
