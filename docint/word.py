

class Word:
    def __init__(self, doc, pageIdx, wordIdx, text, break_type, shape, user_data=None):
        self.doc = doc
        self.page_idx = pageIdx
        self.word_idx = wordIdx

        self._text = text
        self.break_type = "space"

        self._shape = shape
        self.user_data = {} if user_data is None else user_data

    @property
    def text(self):
        return self._text

    @property
    def text_(self):
        return self._text + str(self.break_type)

    @property
    def shape(self):
        return self._shape

    @property
    def box(self):
        return self._shape.box

    @property
    def coords(self):
        return self._shape.coords

    @property
    def path(self):
        return f"page[{self.page_idx}].words[{self.word_idx}]"

    @property
    def path_abbr(self):
        return f"pa{self.page_idx}.wo{self.word_idx}"

    @property
    def xmin(self):
        return self.shape.get_min("x")

    @property
    def xmax(self):
        return self.shape.get_max("x")

    @property
    def ymin(self):
        return self.shape.get_min("y")

    @property
    def ymax(self):
        return self.shape.get_max("y")

    def update_coords(self, coords):
        self.shape.update_coords(coords)

    def in_xrange(self, xrange, partial=False):
        left, right = xrange
        if partial:
            return (left < self.xmin < right) or (left < self.xmax < right)
        else:
            return (left < self.xmin < right) and (left < self.xmax < right)

    def in_yrange(self, yrange, partial=False):
        top, bot = yrange
        if partial:
            return (top < self.ymin < bot) or (top < self.ymax < bot)
        else:
            return (top < self.ymin < bot) and (top < self.ymax < bot)

    def __len__(self):
        return len(self.text)
