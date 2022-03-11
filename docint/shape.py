from typing import List

from pydantic import BaseModel, Field


class Coord(BaseModel):
    x: float
    y: float

    def __str__(self):
        return f'{self.x}:{self.y}'
    


class Shape(BaseModel):
    @classmethod
    def build_box(cls, boxes):
        if isinstance(boxes[0], float):
            coord_vals = boxes
            assert len(coord_vals) == 4
            [x0, y0, x1, y1] = coord_vals
            return Box(top=Coord(x=x0, y=y0), bot=Coord(x=x1, y=y1))
        else:
            xmin, ymin = min([b.xmin for b in boxes]), min([b.ymin for b in boxes])
            xmax, ymax = max([b.xmax for b in boxes]), max([b.ymax for b in boxes])
            return Box(top=Coord(x=xmin, y=ymin), bot=Coord(x=xmax, y=ymax))

    @classmethod
    def build_box_ranges(cls, xrange, yrange):
        return Box(top=Coord(x=xrange[0], y=yrange[0]), bot=Coord(x=xrange[1], y=yrange[1]))


class Box(Shape):
    top: Coord
    bot: Coord

    @classmethod
    def build_box_inpage(cls, bbox, page_size):
        [x0, y0, x1, y1] = bbox
        (w, h) = page_size
        top, bot = Coord(x=x0/w, y=y0/h), Coord(x=x1/w, y=y1/h)
        return Box(top=top, bot=bot)


    
    def __post__init__(self):
        self.check_coords(top, bot)

    def is_box(self):
        return True

    def __str__(self):
        return f'[{self.top}, {self.bot}]'

    @classmethod
    def check_coords(cls, top, bot):
        [minC, maxC] = top, bot
        if (minC.x > maxC.x) or (minC.y > maxC.y):
            raise ValueError("Incorrect order of coords {coords}")

    @property
    def box(self):
        return self

    @property
    def is_horz(self):
        return True if self.width > self.height else False

    @property
    def width(self):
        return self.bot.x - self.top.x

    @property
    def height(self):
        return self.bot.y - self.top.y

    def width_inpage(self, pageSize):
        w, h = pageSize
        return self.width * w

    def height_inpage(self, pageSize):
        w, h = pageSize
        return self.height * h

    def top_inpage(self, pageSize):
        (w, h) = pageSize
        return Coord(x=self.top.x * w, y=self.top.y * h)

    def bot_inpage(self, pageSize):
        (w, h) = pageSize
        return Coord(x=self.bot.x * w, y=self.bot.y * h)

    def size_inpage(self, pageSize):
        return (self.width_inpage(pageSize), self.height_inpage(pageSize))

    @property
    def xmin(self):
        return self.top.x

    @property
    def xmax(self):
        return self.bot.x

    @property
    def ymin(self):
        return self.top.y

    @property
    def ymax(self):
        return self.bot.y

    @property    
    def coords(self):
        return [self.top, self.bot]

    def update_coords(self, coords):
        self.top, self.bot = coords[0], coords[1]

    def get_overlap_percent(self, bigBox):
        (wtop, wbot), (ctop, cbot) = self.coords, bigBox.coords
        (wx0, wy0), (wx1, wy1) = (wtop.x, wtop.y), (wbot.x, wbot.y)
        (cx0, cy0), (cx1, cy1) = (ctop.x, ctop.y), (cbot.x, cbot.y)

        wArea = (wx1 - wx0) * (wy1 - wy0)

        (ox0, oy0) = (max(cx0, wx0), max(cy0, wy0))
        (ox1, oy1) = (min(cx1, wx1), min(cy1, wy1))

        if (ox1 < ox0) or (oy1 < oy0):
            return 0

        if wArea == 0.0:
            return 100

        oArea = (ox1 - ox0) * (oy1 - oy0)
        oPercent = int((oArea / wArea) * 100)
        # logger.debug(f'\t\tWord id: {self.id} overlap: {oPercent}%')
        return oPercent

    def overlaps(self, bigBox, overlap_percent=1.0):
        return True if self.get_overlap_percent(bigBox) > overlap_percent else False

    def in_xrange(self, xrange, partial=False):
        lt, rt = xrange
        xmin, xmax = self.top.x, self.bot.x
        if partial:
            return (lt <= xmin <= rt) or (lt <= xmax <= rt) or (xmin < lt < rt < xmax)
        else:
            return (lt < xmin < rt) and (lt < xmax < rt)

    def in_yrange(self, yrange, partial=False):
        top, bot = yrange
        ymin, ymax = self.top.y, self.bot.y
        if partial:
            return  (top <= ymin <= bot) or (top <= ymax <= bot) or (ymin < top < bot < ymax)
        else:
            return (top < ymin < bot) and (top < ymax < bot)
    

class Poly(Shape):
    coords: List[Coord]
    box_: Box = None
    
    def __post__init__(self):
        self.check_coords(coords)        
        

    @classmethod
    def check_coords(cls, coords):
        # TODO
        return True

    def update_coords(self, coords):
        self.coords = coords
        self.box_ = None

    def is_box(self):
        return False

    def _get_min(self, axis):
        if axis == "x":
            return min([c.x for c in self.coords])
        else:
            return min([c.y for c in self.coords])

    def _get_max(self, axis):
        if axis == "x":
            return max([c.x for c in self.coords])
        else:
            return max([c.y for c in self.coords])

    def is_horz(self):
        (minX, minY) = self.get_min("x"), self.get_min("y")
        (maxX, maxY) = self.get_max("x"), self.get_max("y")
        return True if (maxX - minX) > (maxY - minY) else False

    @property
    def box(self):
        if self.box_ is None:
            (minX, minY) = self._get_min("x"), self._get_min("y")
            (maxX, maxY) = self._get_max("x"), self._get_max("y")
            top, bot = Coord(x=minX, y=minY), Coord(x=maxX, y=maxY)
            self.box_ = Box(top=top, bot=bot)
        return self.box_

    def get_coords_inpage(self, page_size, delim=" "):
        w, h = page_size
        pg_coords = [f"{int(w * c.x)},{int(h * c.y)}" for c in self.coords]
        coord_str = delim.join(pg_coords)
        return coord_str

    @property
    def xmin(self):
        return self.box.top.x

    @property
    def xmax(self):
        return self.box.bot.x

    @property
    def ymin(self):
        return self.box.top.y

    @property
    def ymax(self):
        return self.box.bot.y
    
