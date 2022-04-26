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
    def image_size(self):
        page_image = self.doc.page_images[self.page_idx]
        return (page_image.image_width, page_image.image_height)

    @property
    def text_with_ws(self):
        return ' '.join([w.text_with_ws for w in self.words])
    
    @property
    def shape(self):
        return Box(top=Coord(x=0.0, y=0.0), bot=Coord(x=1.0, y=1.0))

    # TODO fix this, can we move page_image to page
    @property
    def page_image(self):
        page_image = self.doc.page_images[self.page_idx]
        page_image.page = self
        return page_image

    def get_doc_x_val(self, img_x):
        #print(f'img_x: {img_x}')
        page_image = self.doc.page_images[self.page_idx]
        image_box = page_image.image_box

        page_x_scale =  (image_box.bot.x - image_box.top.x) /page_image.image_width
        page_y_scale =  (image_box.bot.y - image_box.top.y) /page_image.image_height
        page_scale = page_x_scale
        
        page_x = img_x * page_scale
        #print(f'page_x: {page_x}')        

        doc_x_val = (page_x + image_box.top.x) / self.width
        #print (f'doc_x_val: {doc_x_val}')
        return doc_x_val

    def get_doc_y_val(self, img_y):
        page_image = self.doc.page_images[self.page_idx]
        image_box = page_image.image_box

        page_y_scale =  (image_box.bot.y - image_box.top.y) /page_image.image_height
        page_y = img_y * page_y_scale

        return (page_y + image_box.top.y) / self.height
    
    def get_image_x_val(self, x):
        #print(f'x: {x}')
        # convert 0.0 - 1.0 coords to page_coords
        page_x = int(x * self.width)

        #print(f'page_x: {page_x}')        
        
        page_image = self.doc.page_images[self.page_idx]
        image_box = page_image.image_box
        
        image_x_scale = page_image.image_width / (image_box.bot.x - image_box.top.x)

        # convert page_coords to image_coords
        image_x_val = int((page_x - image_box.top.x) * image_x_scale)
        #print(f'image_x_val: {image_x_val}')        
        return image_x_val
        
    def get_image_y_val(self, y):
        # convert 0.0 - 1.0 coords to page_coords
        page_y = int(y * self.height)
        
        page_image = self.doc.page_images[self.page_idx]
        image_box = page_image.image_box
        
        image_y_scale = page_image.image_height / (image_box.bot.y - image_box.top.y)

        # convert page_coords to image_coords
        return int((page_y - image_box.top.y) * image_y_scale)


    def words_in_xrange(self, xrange, partial=False):
        return [w for w in self.words if w.box.in_xrange(xrange, partial)]

    def words_in_yrange(self, yrange, partial=False):
        return [w for w in self.words if w.box.in_yrange(yrange, partial)]

    def words_to(self, direction, word, offset=1.0, overlap_percent=1.0, min_height=None):
        if direction not in ("left", "right", "above", "below"):
            raise ValueError(f"Incorrect value of direction {direction}")

        if direction in ("left", "right"):
            if direction == 'left':
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
            #horz_words = self.words_in_xrange(xrange, partial=True)            

            horz_box = Shape.build_box_ranges(xrange, yrange)
            horz_words = [ w for w in horz_words if w.box.overlaps(horz_box, overlap_percent)]
            return Region(words=horz_words)
        else:
            xrange = (word.xmin, word.xmax)
            if direction == 'above':
                top_most = max(0.0, word.ymin - offset)
                yrange = (0.0, word.ymin)
            else:
                bot_most = min(1.0, word.ymax + offste)
                yrange = (word.ymax, bot_most)
            
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

        
