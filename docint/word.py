from enum import IntEnum
from typing import Any, Union

from pydantic import BaseModel

# from .doc import Doc
from .shape import Box, Poly


class BreakType(IntEnum):
    Unknown = 0
    Space = 1
    Sure_space = 2  # very wide
    Eol_sure_space = 3  # line wrapping break
    Hyphen = 4  # end line hyphen that is not in text
    Line_break = 5  # line break that ends paragraph


break_type_str = {
    BreakType.Unknown: " ",
    BreakType.Space: " ",
    BreakType.Sure_space: " ",
    BreakType.Eol_sure_space: " ",
    BreakType.Hyphen: " ",
    BreakType.Line_break: "\n",
}


class Word(BaseModel):
    doc: Any = None
    page_idx: int
    word_idx: int
    text_: str
    break_type: BreakType
    shape_: Union[Poly, Box]
    orig_text_: str = None

    class Config:
        fields = {
            "doc": {"exclude": True},
        }
        use_enum_values = True

    @property
    def text(self):
        return self.text_

    @property
    def orig_text(self):
        return self.orig_text_ if self.orig_text_ is not None else self.text_

    @property
    def text_with_ws(self):
        return self.text_ + break_type_str[self.break_type]

    @property
    def shape(self):
        return self.shape_

    @property
    def box(self):
        return self.shape_.box

    @property
    def coords(self):
        return self.shape_.coords

    @property
    def path(self):
        return f"page[{self.page_idx}].words[{self.word_idx}]"

    @property
    def path_abbr(self):
        return f"pa{self.page_idx}.wo{self.word_idx}"

    @property
    def xmin(self):
        return self.shape_.xmin

    @property
    def xmax(self):
        return self.shape_.xmax

    @property
    def xmid(self):
        return self.shape_.xmid

    @property
    def ymin(self):
        return self.shape_.ymin

    @property
    def ymax(self):
        return self.shape_.ymax

    @property
    def ymid(self):
        return self.shape_.ymid

    @property
    def page(self):
        return self.doc.pages[self.page_idx]

    @property
    def alt_text(self):
        return self.text

    def update_coords(self, coords):
        self.shape.update_coords(coords)

    def __bool__(self):
        # A word is not valid if it is empty, but needs to be kept
        # for various reasons.
        return bool(self.text_)

    def correct_word(self, correct_text):
        self.text_ = correct_text

    # edit words
    # TODO: Should we add more info in the word or keep that info
    # at top level, currently thinking top level, then why should we
    # store orig_ Check issue #13

    def clear(self, clearChar=None):
        old = "<all>" if clearChar is None else clearChar
        self.replaceStr(old, "")

    def replaceStr(self, old, new):
        if self.orig_text_ is None:
            self.orig_text_ = self.text_

        if old.lower() == "<all>":
            self.text_ = new
        else:
            self.text_ = self.text_.replace(old, new)

    def mergeWord(self, next_word):
        if self.orig_text_ is None:
            self.orig_text_ = self.text_

        if next_word.orig_text_ is None:
            next_word.orig_text_ = next_word.text_

        top = self.box.top
        bot = next_word.box.bot

        self.text_ += next_word.text_
        next_word.text_ = ""

        self.shape_ = Box(top=top, bot=bot)

    def __len__(self):
        return len(self.text)
