from dataclasses import dataclass
from enum import Enum
import string

from ..vision import Vision
from ..region import Region
from ..util import load_config


class NumType(Enum):
    NotNumber = 0
    Ordinal = 1
    Roman = 2
    Alphabet = 3


class NumMarker(Region):
    def __init__(self, num_type, num_text, num_val, word, idx):
        super().__init__(word.doc, word.page_idx, [word])
        self.num_type = num_type
        self.num_text = num_text
        self.num_val = num_val
        self.idx = idx

    def set_idx(self, idx):
        self.idx = idx

    @property
    def path_abbr(self):
        return f"p{self.page_idx}.nummarker{self.idx}"

@Vision.factory(
    "num_marker",
    default_config={
        "doc_confdir": "conf",
        "min_marker": 3,
        "pre_edit": True,
        "find_ordinal": True,
        "find_roman": True,
        "find_alphabet": False,
        "x_search_range": (0, 0.45),
        "y_search_range": (0, 1.0),
        "num_chars": ".,()",
        "max_number": 49,
    },
)
class FindNumMarker:
    def __init__(
        self,
        doc_confdir,
        min_marker,
        pre_edit,
        find_ordinal,
        find_roman,
        find_alphabet,
        x_search_range,
        y_search_range,
        num_chars,
        max_number,
    ):
        self.doc_confdir = doc_confdir
        self.min_marker = min_marker
        self.pre_edit = pre_edit
        self.find_ordinal = find_ordinal
        self.find_roman = find_roman
        self.find_alphabet = find_alphabet
        self.x_search_range = x_search_range
        self.y_search_range = y_search_range
        self.num_chars = num_chars
        self.max_number = max_number
        self.roman_dict = self.build_roman_dict()
        self.alpha_dict = self.build_alphabet_dict()

    def build_roman_dict(self):
        rS = (
            "0,i,ii,iii,iv,v,vi,vii,viii,ix,x,xi,xii,xiii,xiv,xv,"
            + "xvi,xvii,xviii,xix,xx,xxi,xxii,xxiii,xxiv,xxv,xxvi,xxvii,"
            + "xxviii,xxix,xxx,xxxi,xxxii,xxxiii,xxxiv,xxxv,xxxvi,xxxvii,"
            + "xxxviii,xxxix,xxxx,xxxxi,xxxxii,xxxxiii,xxxxiv,xxxxv,xxxxvi"
        )
        return dict([(r, idx) for (idx, r) in enumerate(rS.split(","))])

    def build_alphabet_dict(self):
        return dict([(c, idx + 1) for (idx, c) in enumerate(string.ascii_lowercase)])

    def find_number(self, text):
        def is_roman(c):
            return c in "ivx"

        def is_alphabet(c):
            return c in string.ascii_lowercase

        text = text.strip().strip(self.num_chars).strip()
        text = text.replace("х", "x").replace("і", "i")  # replace unicode chars

        if all(c.isdigit() for c in text):
            num_type = NumType.Ordinal
            num_val = int(text)
        elif all([is_roman(c) for c in text]):
            num_type = NumType.Roman
            num_val = self.roman_dict(text)
        elif all([is_alphabet(c) for c in text]) and len(text) == 1:
            num_type = NumType.Alphabet
            num_val = self.alpha_dict(text)
        else:
            num_type = NumType.NotNumber
            num_val = None

        return num_type, text, num_val

    def build_marker(self, word):
        (num_type, num_text, num_val) = self.find_number(word.text)
        num_marker = NumMarker(num_type, num_text, num_val, word, word.word_idx)
        return num_marker

    def isEmpty(self, region, ignorePunct=False):
        if not region:
            return True
        
        if ignorePunct:
            return True if (not region.text) or (not text.isalnum()) else False
        else:
            return True if not region.text else False

    def is_valid(self, page, word, marker):
        if marker.num_type == NumType.NotNumber:
            return False

        if marker.num_val > self.max_number:
            return False

        if not (
            word.in_xrange(self.x_search_range) and word.in_yrange(self.y_search_range)
        ):
            return False

        ltWords = page.words_to("left", word)
        if not self.isEmpty(ltWords, ignorePunct=True):
            return False

        return True

    def __call__(self, doc):
        doc_config = load_config(self.doc_confdir, doc.pdf_name, "nummarker")

        if self.pre_edit:
            doc.edit(doc_config.get("edits", []))

        for page in doc.pages:
            markers = [self.build_marker(w) for w in page.words]
            z_pgmks = zip(page.words, markers)
            num_markers = [m for (w, m) in z_pgmks if self.is_valid(page, w, m)]

            [ m.set_idx(idx) for idx, m in enumerate(num_markers)]
            page.num_markers = num_markers
        return doc
