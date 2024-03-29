from itertools import chain
from typing import List

from pydantic import BaseModel

from .shape import Box, Coord, Shape
from .word import Word


class Region(BaseModel):
    word_idxs: List[int]
    page_idx_: int = None

    words: List[Word] = None
    shape_: Box = None

    class Config:
        fields = {
            "words": {"exclude": True},
            "shape_": {"exclude": True},
        }

    @classmethod
    def from_words(cls, words):
        word_idxs = [w.word_idx for w in words]
        return Region(words=words, word_idxs=word_idxs, page_idx_=words[0].page_idx)

    @classmethod
    def no_words(cls, page_idx):
        return Region(words=[], word_idxs=[], page_idx_=page_idx)

    # TODO REMOVE
    @classmethod
    def build(cls, words, page_idx):
        word_idxs = [w.word_idx for w in words]
        return Region(words=words, word_idxs=word_idxs, page_idx_=page_idx)

    @classmethod
    def get_relevant_objects(cls, regions, path, shape):
        def get_path_page_idx(path):
            page_idx, word_idx = path.split(".", 1)
            return int(page_idx[2:])

        relevant_regions = []
        path_page_idx = get_path_page_idx(path)

        for region in regions:
            if not region.words:
                continue

            if region.page.page_idx != path_page_idx:
                continue

            if shape.box.overlaps(region.shape.box, 80):
                relevant_regions.append(region)
        return relevant_regions

    def __len__(self):
        return len(self.words)

    def __getitem__(self, idx):
        print("Inside __get__item")
        if isinstance(idx, slice):
            sl = idx
            return Region.build(self.words[sl], self.page_idx)
        elif isinstance(idx, int):
            if idx >= len(self.words):
                print(f"Unknown idx: {idx}")
            return self.words[idx]
        else:
            raise TypeError("Unknown type {type(idx)} this method can handle")

    def __iter__(self):
        return iter(self.words)

    def __bool__(self):
        return True if self.word_idxs else False

    # TODO_MUST shouldn't this be in para.py ???
    def remove_word_ifpresent(self, word):
        rm_idx = word.word_idx
        if rm_idx in self.word_idxs:
            self.word_idxs = [idx for idx in self.word_idxs if rm_idx != idx]
            self.words = [w for w in self.words if w.word_idx != rm_idx]
            self.shape_ = None

            # if self.word_lines:
            #     word_lines = []
            #     for word_line in self.word_lines:
            #         word_lines.append([w for w in word_line if w.word_idx != rm_idx])
            #     self.word_lines = word_lines

            # if self.word_lines_idxs:
            #     word_lines_idxs = []
            #     for word_line_idx in self.word_lines_idxs:
            #         word_lines_idxs.append([idx for idx in word_line_idx if idx != rm_idx])
            #     self.word_lines_idxs = word_lines_idxs

    # def __bool__(self):
    #     # What is an empty region, what if remove the words from a
    #     # a region after words
    #     return bool(self.words)

    @property
    def doc(self):
        return self.words[0].doc

    @property
    def page_idx(self):
        return self.page_idx_

    @property
    def page(self):
        return self.doc.pages[self.page_idx_]

    def get_regions(self):
        return [self]

    def text_len(self):
        # should we eliminate zero words ? not now
        text_lens = [len(w.text) for w in self.words]
        num_spaces = len(text_lens) - 1
        return sum(text_lens) + num_spaces if text_lens else 0

    def text_isalnum(self):
        # should we eliminate zero words ? not now
        return all([w.text.isalnum() for w in self.words])

    def raw_text(self):
        word_texts = [w.text for w in self.words if w]
        return " ".join(word_texts)

    def text_with_break(self):
        return "".join(w.text_with_break(ignore_line_break=True) for w in self.words)

    def arranged_words(self, words, cutoff_thous=5):
        def centroid(line):
            return line[-1].ymid

        if not words:
            return []

        word_lines = [[]]
        words = sorted(words, key=lambda w: w.ymid)
        word_lines[0].append(words.pop(0))

        for word in words:
            last_centroid = centroid(word_lines[-1])

            if (word.ymid - last_centroid) * 1000 > cutoff_thous:
                word_lines.append([word])
            else:
                word_lines[-1].append(word)

        [line.sort(key=lambda w: w.xmin) for line in word_lines]
        return list(chain(*word_lines))

    def arranged_text(self, cutoff_thous=5):
        arranged_words = self.arranged_words(self.words, cutoff_thous)
        word_texts = [w.text for w in arranged_words if w]
        return " ".join(word_texts)

    def orig_text(self):
        word_texts = [w.orig_text for wl in self.word_lines for w in wl if w.orig_text]
        return " ".join(word_texts)

    @property
    def shape(self):
        if self.shape_ is None:
            self.shape_ = Shape.build_box([w.box for w in self.words])
        return self.shape_

    @property
    def box(self):
        return self.shape.box

    @property
    def xmin(self):
        return self.shape.xmin

    @property
    def xmax(self):
        return self.shape.xmax

    @property
    def xmid(self):
        return self.shape.xmid

    @property
    def ymin(self):
        return self.shape.ymin

    @property
    def ymax(self):
        return self.shape.ymax

    @property
    def ymid(self):
        return self.shape.ymid

    def get_box_to_svg(self):
        image_box = self.page.get_image_shape(self.shape)
        return [image_box.top.x, image_box.top.y, image_box.bot.x, image_box.bot.y]

    def update_links(self, doc):
        for region in self.get_regions():
            region.words = [doc[region.page_idx_][idx] for idx in region.word_idxs]
            if hasattr(region, "word_lines_idxs") and region.word_lines_idxs is not None:
                p_idx, wl_idxs = region.page_idx_, region.word_lines_idxs
                region.word_lines = [[doc[p_idx][idx] for idx in wl] for wl in wl_idxs]

    def reduce_width_at(self, direction, ov_shape):
        # edit, word_line
        # reduce with only of the box
        assert direction in ("left", "right")
        box = self.shape.box

        assert len(self.words) == 1

        # print(f'\tReducing width >{self.words[0].text}< self:{box} ov:{ov_shape} {direction}')
        inc = 0.000001
        inc = 0.001

        if direction == "left":
            assert self.xmin <= ov_shape.xmax
            new_top = Coord(x=ov_shape.xmax + inc, y=box.top.y)
            self.words[0].shape.box.update_coords([new_top, self.shape.box.bot])
            self.shape_ = None
        else:
            assert self.xmax >= ov_shape.xmin
            new_bot = Coord(x=ov_shape.xmin - inc, y=box.bot.y)
            self.words[0].shape.box.update_coords([self.shape.box.top, new_bot])
            self.shape_ = None

        box = self.shape.box
        # print(f'\tReduced  width >{self.words[0].text}< self:{box} ov:{ov_shape} xmin:{self.xmin} xmax: {self.xmax}')
