from typing import List
from typing import Any

from pydantic import BaseModel, Field, Extra

#from .doc import Doc
from .region import Region
from .shape import Shape, Box, Coord
from .word import Word, BreakType


class Page(BaseModel):
    doc: Any
    page_idx: int
    words: List[Word]
    width_: int
    height_: int

    class Config:
        extra = 'allow'
        fields = {'doc': {'exclude': True}}
        
        json_encoders = {
            Word: lambda w: f'{w.page_idx}-{w.word_idx}',
        }
        


    def __getitem__(self, idx):
        if isinstance(idx, slice):
            Region(self.doc, self.page_idx, self.words[idx])
        elif isinstance(idx, int):  # should I return a region ?
            return self.words[idx]
        else:
            raise TypeError("Unknown type {type(idx)} this method can handle")

    def get_region(self, shape, overlap=100):
        assert False
        pass

    def get_text_at(self, direction, word, use_ordered=False):
        assert False        
        if direction not in ("left", "right"):
            raise ValueError()
        pass

    def get_ordered_words(self):
        assert False        
        pass
        # Should this be outside ???

    def orient_page(self):
        assert False        
        pass

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
        return ' '.join([w.text for w in self.words])

    @property
    def text_with_ws(self):
        return ' '.join([w.text_with_ws for w in self.words])
    
    @property
    def shape(self):
        return Box(top=Coord(x=0.0, y=0.0), bot=Coord(x=1.0, y=1.0))

    def words_in_xrange(self, xrange, partial=False):
        return [w for w in self.words if w.box.in_xrange(xrange, partial)]

    def words_in_yrange(self, yrange, partial=False):
        return [w for w in self.words if w.box.in_yrange(yrange, partial)]

    def words_to(self, direction, word, overlap_percent=1.0, min_height=None):
        if direction not in ("left", "right", "up", "down"):
            raise ValueError(f"Incorrect value of direction {direction}")

        if direction in ("left", "right"):
            xrange = (0.0, word.xmin) if direction == "left" else (word.xmax, 1.0)
            if min_height and word.box.height < min_height:
                height_inc = (min_height - word.box.height) / 2.0
                yrange = (word.ymin - height_inc, word.ymax + height_inc)
            else:
                yrange = (word.ymin, word.ymax)

            horz_words = self.words_in_yrange(yrange, partial=True)
            #horz_words = self.words_in_xrange(xrange, partial=True)            

            horz_box = Shape.build_box_ranges(xrange, yrange)
            horz_words = [ w for w in horz_words if w.box.overlaps(horz_box, overlap_percent)]
            return Region(words=horz_words)
        else:
            xrange = (word.xmin, word.xmax)
            yrange = (0.0, word.ymin) if direction == "top" else (word.ymax, 1.0)

            vert_words = self.words_in_xrange(xrange, partial=True)

            vert_box = Shape.build_box_ranges(xrange, yrange)
            vert_words = [ w for w in vert_words if w.box.overlaps(vert_box, overlap_percent)]
            return Region(words=vert_words)

    # edit methods
    def add_word(self, text, box):
        word_idx = len(self.words)
        
        word = Word(doc=self.doc, page_idx=self.page_idx, word_idx=word_idx, text_=text, break_type=BreakType.Space, shape_=box)
        self.words.append(word)

    @property
    def page(self):
        return self
    
