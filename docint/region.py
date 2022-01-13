from .shape import Shape

class Region:
    @classmethod
    def build_region(cls, words):
        if not words:
            return None
        else:
            return Region(words[0].doc, words[0].page_idx, words)
    
    def __init__(self, doc, page_idx, words):
        self.doc = doc
        self.page_idx = page_idx
        self.words = words
        self._text = None
        self._shape = None


    @property
    def text(self):
        if self._text is None:
            self._text = ' '.join([w.text for w in self.words])
        return self._text

    @property
    def shape(self):
        if self._shape is None:
            self._shape = Shape.build_box([w.box for w in self.words])
        return self._shape
        

