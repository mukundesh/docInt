from .region import Region
from .shape import Shape


class Page:
    def __init__(self, doc, pageIdx, width, height, user_data=None):
        self.doc = doc
        self.pageIdx = pageIdx
        self.user_data = {} if user_data is None else user_data
        self.words = []
        self._width = width
        self._height = height

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            Region(self.doc, self.pageIdx, self.words[idx])
        elif isinstance(idx, int):  # should I return a region ?
            return self.words[idx]
        else:
            raise TypeError("Unknown type {type(idx)} this method can handle")

    def get_region(self, shape, overlap=100):
        pass

    def get_text_at(self, direction, word, use_ordered=False):
        if direction not in ("left", "right"):
            raise ValueError()
        pass

    def get_ordered_words(self):
        pass
        # Should this be outside ???

    def orient_page(self):
        pass

    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def size(self):
        return (self._width, self._height)

    def words_in_xrange(self, xrange, partial=False):
        return [w for w in self if w.in_xrange(xrange, partial)]

    def words_in_yrange(self, yrange, partial=False):
        return [w for w in self if w.in_yrange(yrange, partial)]

    def words_to(self, direction, word, overlap_percent=1.0):
        if direction not in ("left", "right", "up", "down"):
            raise ValueError(f"Incorrect value of direction {direction}")

        if direction in ("left", "right"):
            xrange = (0.0, word.xmin) if direction == "left" else (word.xmax, 1.0)
            yrange = (word.ymin, word.ymax)

            horz_words = self.words_in_yrange(yrange, partial=True)
            horz_words = [ w for w in horz_words if w.in_xrange(xrange, partial=True)]

            horz_box = Shape.build_box_ranges(xrange, yrange)
            horz_words = [w.box.overlaps(horz_box, overlap_percent) for w in horz_words]
            return Region.build_region(horz_words)
        else:
            xrange = (word.xmin, word.xmax)
            yrange = (0.0, word.ymin) if direction == "top" else (word.ymax, 1.0)

            vert_words = self.words_in_yrange(yrange, partial=True)
            vert_words = [ w for w in vert_words if w.in_xrange(xrange, partial=True)]

            vert_box = Shape.build_box_ranges(xrange, yrange)
            vert_words = [w.box.overlaps(vert_box, overlap_percent) for w in vert_words]
            return Region.build_region(vert_words)

    @property
    def page(self):
        return self
