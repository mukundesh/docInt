import math
from typing import List

from pydantic import BaseModel


class Coord(BaseModel):
    x: float  # currently always stay as float
    y: float

    def __str__(self):
        return f"{self.x:4.4f}:{self.y:4.4f}"

    def inside(self, top, bot):
        return (top.x <= self.x <= bot.x) and (top.y <= self.y <= bot.y)


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
    def build(self, coords):
        assert len(coords) >= 2
        xmin, xmax = min(c.x for c in coords), max(c.x for c in coords)
        ymin, ymax = min(c.y for c in coords), max(c.y for c in coords)
        return Box(top=Coord(x=xmin, y=ymin), bot=Coord(x=xmax, y=ymax))

    def __post_init__(self):
        # TODO move this somewhere else ?
        self.check_coords(self.top, self.bot)

    def is_box(self):
        return True

    def __str__(self):
        return f"[{self.top}, {self.bot}]"

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

    @property
    def size(self):
        return (self.width, self.height)

    @property
    def xmin(self):
        return self.top.x

    @property
    def xmax(self):
        return self.bot.x

    @property
    def xmid(self):
        return (self.top.x + self.bot.x) / 2

    @property
    def ymin(self):
        return self.top.y

    @property
    def ymax(self):
        return self.bot.y

    @property
    def ymid(self):
        return (self.top.y + self.bot.y) / 2

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
            return (top <= ymin <= bot) or (top <= ymax <= bot) or (ymin < top < bot < ymax)  # noqa: W503  # noqa: W503
        else:
            return (top < ymin < bot) and (top < ymax < bot)


class Poly(Shape):
    coords: List[Coord]
    box_: Box = None

    class Config:
        fields = {
            "box_": {"exclude": True},
        }

    def __post_init__(self):
        self.check_coords(self.coords)

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

    @property
    def xmin(self):
        return self.box.top.x

    @property
    def xmax(self):
        return self.box.bot.x

    @property
    def xmid(self):
        return self.box.xmid

    @property
    def ymin(self):
        return self.box.top.y

    @property
    def ymax(self):
        return self.box.bot.y

    @property
    def ymid(self):
        return self.box.ymid


class Edge(Shape):
    coord1: Coord
    coord2: Coord
    orientation: str

    @classmethod
    def build_v(cls, x1, y1, x2, y2):
        c1 = Coord(x=x1, y=y1)
        c2 = Coord(x=x2, y=y2)
        return Edge(coord1=c1, coord2=c2, orientation="v")

    @classmethod
    def build_h(cls, x1, y1, x2, y2):
        c1 = Coord(x=x1, y=y1)
        c2 = Coord(x=x2, y=y2)
        return Edge(coord1=c1, coord2=c2, orientation="h")

    @classmethod
    def build_v_oncoords(cls, c1, c2):
        return Edge(coord1=c1, coord2=c2, orientation="v")

    @classmethod
    def build_h_oncoords(cls, c1, c2):
        return Edge(coord1=c1, coord2=c2, orientation="h")

    @property
    def xmin(self):
        return min(self.coord1.x, self.coord2.x)

    @property
    def xmax(self):
        return max(self.coord1.x, self.coord2.x)

    @property
    def xmid(self):
        return (self.coord1.x + self.coord2.x) / 2

    @property
    def ymin(self):
        return min(self.coord1.y, self.coord2.y)

    @property
    def ymax(self):
        return max(self.coord1.y, self.coord2.y)

    @property
    def ymid(self):
        return (self.coord1.y + self.coord2.y) / 2

    @property
    def coords(self):
        return [self.coord1, self.coord2]

    @property
    def length(self):
        c1, c2 = self.coords
        return math.sqrt((c2.x - c1.x) ** 2 + (c2.y - c1.y) ** 2)

    def get_coord(self, length_ratio):
        """Get the coordinates of the point at length ratio from c1"""
        c1, c2 = self.coord1, self.coord2

        if (c1.x == c2.x) or (c1.y == c2.y):
            if self.orientation == "h":
                assert c1.y == c2.y
                x = c1.x + ((c2.x - c1.x) * length_ratio)
                return Coord(x=x, y=c1.y)
            else:
                assert c1.x == c2.x
                y = c1.y + ((c2.y - c1.y) * length_ratio)
                return Coord(x=c1.x, y=y)
        else:
            slope = (c2.y - c1.y) / (c2.x - c1.x)
            angle = math.atan(slope)
            x = c1.x + (length_ratio * self.length) * math.cos(angle)
            y = c1.y + (length_ratio * self.length) * math.sin(angle)
            return Coord(x=x, y=y)

    @property
    def alt_text(self):
        def percent(v):
            return int(100 * v)

        ts = [f"{percent(c.x)},{percent(c.y)}" for c in self.coords]
        return "->".join(ts)

    def is_box(self):
        return False

    @property
    def shape(self):
        return self

    @property
    def path_abbr(self):
        return "edge"

    def cross(self, edge):
        return Edge.intersection(self, edge)

    # https://stackoverflow.com/questions/20677795/how-do-i-compute-the-intersection-point-of-two-lines
    @classmethod
    def intersection(cls, edge1, edge2):
        xdiff = (edge1.coord1.x - edge1.coord2.x, edge2.coord1.x - edge2.coord2.x)
        ydiff = (edge1.coord1.y - edge1.coord2.y, edge2.coord1.y - edge2.coord2.y)

        def coord_pair(edge):
            return ((edge.coord1.x, edge.coord1.y), (edge.coord2.x, edge.coord2.y))

        def det(a, b):
            return a[0] * b[1] - a[1] * b[0]

        div = det(xdiff, ydiff)
        if div == 0:
            raise Exception("lines do not intersect")

        d = (det(*coord_pair(edge1)), det(*coord_pair(edge2)))
        x = det(d, xdiff) / div
        y = det(d, ydiff) / div
        return Coord(x=x, y=y)


# Poly
# def get_coords_inpage(self, page_size, delim=" "):
#     w, h = page_size
#     pg_coords = [f"{int(w * c.x)},{int(h * c.y)}" for c in self.coords]
#     coord_str = delim.join(pg_coords)
#     return coord_str

# def get_coords_inimage(self, page, delim=" "):
#     def get_image_val(c, axis):
#         if axis == 'x':
#             return page.get_image_x_val(c.x)
#         else:
#             return page.get_image_y_val(c.y)
#     pg_vals = [f"{get_image_val(c, 'x')},{get_image_val(c, 'y')}" for c in self.coords]
#     coord_str = delim.join(pg_vals)
#     return coord_str


# Box
# @classmethod
# def build_box_inpage(cls, bbox, page_size):
#     [x0, y0, x1, y1] = bbox
#     (w, h) = page_size
#     top, bot = Coord(x=x0/w, y=y0/h), Coord(x=x1/w, y=y1/h)
#     return Box(top=top, bot=bot)


# Box
# def width_inpage(self, pageSize):
#     w, h = pageSize
#     return self.width * w

# def height_inpage(self, pageSize):
#     w, h = pageSize
#     return self.height * h

# def top_inpage(self, pageSize):
#     (w, h) = pageSize
#     return Coord(x=self.top.x * w, y=self.top.y * h)

# def bot_inpage(self, pageSize):
#     (w, h) = pageSize
#     return Coord(x=self.bot.x * w, y=self.bot.y * h)

# def top_inimage(self, page):
#     return Coord(x=page.get_image_x_val(top.x), y=page.get_image_y_val(top.y))

# def size_inpage(self, pageSize):
#     return (self.width_inpage(pageSize), self.height_inpage(pageSize))

# def size_inimage(self, page):
#    page_image = page.doc.page_images[self.page_idx]
#    return (page_image.image_width, page_image.image_height)


# Edge
# def get_coords_inpage(self, page_size, delim=" "):
#     w, h = page_size
#     pg_coords = [f"{int(w * c.x)},{int(h * c.y)}" for c in self.coords]
#     coord_str = delim.join(pg_coords)
#     return coord_str

# def get_coords_inimage(self, page, delim=" "):
#     def get_image_val(c, axis):
#         if axis == 'x':
#             return page.get_image_x_val(c.x)
#         else:
#             return page.get_image_y_val(c.y)
#     pg_vals = [f"{get_image_val(c, 'x')},{get_image_val(c, 'y')}" for c in self.coords]
#     coord_str = delim.join(pg_vals)
#     return coord_str
