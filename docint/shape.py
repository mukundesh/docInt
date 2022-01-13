from dataclasses import dataclass


class Coord:
    def __init__(self, x, y):
        assert not isinstance(x, list)
        assert not isinstance(y, list)        
        self.x = x
        self.y = y

class Shape:
    @classmethod
    def build_box(cls, boxes):
        xmin, ymin = min([b.get_min('x') for b in boxes]), min([b.get_min('y') for b in boxes])
        xmax, ymax = max([b.get_max('x') for b in boxes]), max([b.get_max('y') for b in boxes])
        return Box([Coord(xmin, ymin), Coord(xmax, ymax)])

    @classmethod
    def build_box_ranges(cls, xrange, yrange):
        return Box([Coord(xrange[0], yrange[0]), Coord(xrange[1], yrange[1])])


class Poly(Shape):
    def __init__(self, coords):
        self.check_coords(coords)
        self.coords = coords
        self._box = None

    @classmethod
    def check_coords(cls, coords):
        # TODO
        return True

    def is_box(self):
        return False

    def get_min(self, axis):
        if axis == "x":
            return min([c.x for c in self.coords])
        else:
            return min([c.y for c in self.coords])

    def get_max(self, axis):
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
        if self._box is None:
            (minX, minY) = self.get_min("x"), self.get_min("y")
            (maxX, maxY) = self.get_max("x"), self.get_max("y")
            top, bot = Coord(minX, minY), Coord(maxX, maxY)
            self._box = Box([top, bot])
        return self._box

    def get_coords_inpage(self, page_size, delim=" "):
        w, h = page_size
        pg_coords = [f"{int(w * c.x)},{int(h * c.y)}" for c in self.coords]
        coord_str = delim.join(pg_coords)
        return coord_str


class Box(Shape):
    def __init__(self, coords):
        self.check_coords(coords)
        self.coords = coords

    def is_box(self):
        return True

    @classmethod
    def check_coords(cls, coords):
        if len(coords) != 2:
            raise ValueError("Expected two coords, instead got {len(coords)}")

        [minC, maxC] = coords
        if (minC.x > maxC.x) or (minC.y > maxC.y):
            raise ValueError("Incorrect order of coords {coords}")

    @property
    def box(self):
        return self

    @property
    def is_horz(self):
        return True if self.width > self.height else False

    @property
    def top(self):
        return self.coords[0]

    @property
    def bot(self):
        return self.coords[1]

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
        return Coord(self.top.x * w, self.top.y * h)


    def bot_inpage(self, pageSize):
        (w, h) = pageSize
        return Coord(self.bot.x * w, self.bot.y * h)

    def size_inpage(self, pageSize):
        return (self.width_inpage(pageSize), self.height_inpage(pageSize))
    
    def get_min(self, axis):
        return self.top.x if axis == "x" else self.top.y

    def get_max(self, axis):
        return self.bot.x if axis == "x" else self.bot.y

    def overlapPercent(self, bigBox):
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

    def overlaps(self, bigBox, overlap_percent):
        return True if self.overlap_percent(bigBox) > overlap_percent else False
