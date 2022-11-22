import logging
import string
import sys
from enum import IntEnum
from itertools import chain
from pathlib import Path
from typing import Union

from ..data_error import DataError
from ..region import Region
from ..shape import Box, Coord
from ..util import load_config
from ..vision import Vision


class NumType(IntEnum):
    NotNumber = 0
    Ordinal = 1
    Roman = 2
    Alphabet = 3


class NumMarker(Region):
    num_type: NumType
    num_text: str
    num_val: Union[int, None]
    idx: int

    def set_idx(self, idx):
        self.idx = idx

    def __str__(self):
        return f"{self.num_text}"

    @property
    def path_abbr(self):
        return f"p{self.page_idx}.nummarker{self.idx}"

    @property
    def word_idx(self):
        return self.words[0].word_idx

    @property
    def alt_text(self):
        return self.num_text

    @classmethod
    def build(cls, num_type, num_text, num_val, word):
        word_idxs = [word.word_idx]
        page_idx = word.page_idx
        return NumMarker(
            words=[word],
            word_idxs=word_idxs,
            page_idx_=page_idx,
            num_type=num_type,
            num_text=num_text,
            num_val=num_val,
            idx=word.word_idx,
        )

    @classmethod
    def get_relevant_objects(cls, markers, path, shape):
        path_page_idx, _ = path.split(".", 1)
        path_page_idx = int(path_page_idx[2:])

        sb = shape.box
        expanded_box = Box(top=Coord(x=0.0, y=sb.top.y), bot=Coord(x=1.0, y=sb.bot.y))

        relevant_markers = []
        for marker in markers:
            if marker.page_idx != path_page_idx:
                continue

            if marker.shape.box.overlaps(expanded_box, 80):
                relevant_markers.append(marker)

        return relevant_markers

    def get_html_lines(self):
        return [f"Num Marker: {self.num_text}, Val: {self.num_val}, Type: {self.num_type}"]

    def get_html_json(self):
        return f"{{ text: {self.num_text}, val: {self.num_val} type: {self.num_type} }}"


class MarkerMisalginedError(DataError):
    exp_val: int
    act_val: int
    word_idx: int


@Vision.factory(
    "num_marker",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "nummarker",
        "min_marker": 3,
        "pre_edit": True,
        "find_ordinal": True,
        "find_roman": True,
        "find_alphabet": False,
        "x_range": (0, 0.45),
        "y_range": (0, 1.0),
        "num_chars": ".,()",
        "max_number": 49,
        "page_idxs": [],
        "include_zero": False,
    },
)
class FindNumMarker:
    def __init__(
        self,
        conf_dir,
        conf_stub,
        min_marker,
        pre_edit,
        find_ordinal,
        find_roman,
        find_alphabet,
        x_range,
        y_range,
        num_chars,
        max_number,
        page_idxs,
        include_zero,
    ):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = conf_stub
        self.min_marker = min_marker
        self.pre_edit = pre_edit
        self.find_ordinal = find_ordinal
        self.find_roman = find_roman
        self.find_alphabet = find_alphabet
        self.x_range = x_range
        self.y_range = y_range
        self.num_chars = num_chars
        self.max_number = max_number
        self.page_idxs = page_idxs
        self.include_zero = include_zero

        self.roman_dict = self.build_roman_dict()
        self.alpha_dict = self.build_alphabet_dict()

        self.valid_num_types = self.get_valid_types()

        self.lgr = logging.getLogger(f"docint.pipeline.{self.conf_stub}")
        self.lgr.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)

        self.file_handler = None
        self.info_dict = {}

    def get_valid_types(self):
        num_types = []
        if self.find_alphabet:
            num_types.append(NumType.Alphabet)
        if self.find_roman:
            num_types.append(NumType.Roman)
        if self.find_ordinal:
            num_types.append(NumType.Ordinal)
        return num_types

    def add_log_handler(self, doc):
        handler_name = f"{doc.pdf_name}.{self.conf_stub}.log"
        log_path = Path("logs") / handler_name
        self.file_handler = logging.FileHandler(log_path, mode="w")
        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def build_roman_dict(self):
        rS = (
            "0,i,ii,iii,iv,v,vi,vii,viii,ix,x,xi,xii,xiii,xiv,xv,"  # noqa: W503
            + "xvi,xvii,xviii,xix,xx,xxi,xxii,xxiii,xxiv,xxv,xxvi,xxvii,"  # noqa: W503
            + "xxviii,xxix,xxx,xxxi,xxxii,xxxiii,xxxiv,xxxv,xxxvi,xxxvii,"  # noqa: W503
            + "xxxviii,xxxix,xxxx,xxxxi,xxxxii,xxxxiii,xxxxiv,xxxxv,xxxxvi"  # noqa: W503
        )
        return dict([(r, idx) for (idx, r) in enumerate(rS.split(","))])

    def build_alphabet_dict(self):
        return dict([(c, idx + 1) for (idx, c) in enumerate(string.ascii_lowercase)])

    def find_number(self, text, word_idx):
        def is_roman(c):
            return c in "ivx"

        def is_alphabet(c):
            return c in string.ascii_lowercase

        text = text.strip().strip(self.num_chars).strip()
        text = text.replace("х", "x").replace("і", "i")  # replace unicode chars
        text = text.replace("X", "x")  # replace 'X' not 'V' as it is in names

        if text == "":
            num_type = NumType.NotNumber
            num_val = None
        elif all(c.isdigit() for c in text):
            num_type = NumType.Ordinal
            num_val = int(text)
        elif all([is_roman(c) for c in text]):
            num_type = NumType.Roman
            num_val = self.roman_dict[text]
        elif all([is_alphabet(c) for c in text]) and len(text) == 1:
            num_type = NumType.Alphabet
            num_val = self.alpha_dict[text]
        else:
            num_type = NumType.NotNumber
            num_val = None

        self.lgr.debug(f"{word_idx} num_type: {num_type} text: {text} num_val: {num_val}")
        return num_type, text, num_val

    def build_marker(self, word):
        (num_type, num_text, num_val) = self.find_number(word.text, word.word_idx)
        num_marker = NumMarker.build(num_type, num_text, num_val, word)
        return num_marker

    def is_empty(self, region, ignorePunct=False):
        if not region:
            return True

        if ignorePunct:
            return True if (region.text_len() == 0) or (not region.text_isalnum()) else False
        else:
            return True if region.text_len() == 0 else False

    def is_valid(self, page, word, marker):
        def less_than_zero(num_val):
            if self.include_zero:
                return num_val < 0
            else:
                return num_val <= 0

        if marker.num_type == NumType.NotNumber:
            return False

        if marker.num_type not in self.valid_num_types:
            return False

        if marker.num_val > self.max_number or less_than_zero(marker.num_val):
            self.lgr.debug(f"\t{word.text}[{word.word_idx}] not in [0, {self.max_number}]")
            return False

        if not (word.box.in_xrange(self.x_range) and word.box.in_yrange(self.y_range)):
            self.lgr.debug(f"\t{word.text} {word.xmin}:{word.xmax} outside {self.x_range} {self.y_range}")
            return False

        lt_words = page.words_to("left", word)
        if not self.is_empty(lt_words, ignorePunct=True):
            lt_text = " ".join(w.text for w in lt_words.words)
            self.lgr.debug(
                f"\t{word.text} lt_words.text_len() {lt_words.text_len()} {lt_text} {lt_words.words[0].word_idx} {lt_words.words[0].xmin} {lt_words.words[0].xmax}"
            )
            return False

        self.lgr.debug(f"\t{word.text} True")
        return True

    def get_fix(self, error):
        e = error
        page_path, marker_path = e.path.split(".")
        word_path = f"{page_path}.wo{e.word_idx}"
        msg = f"{e.path} {e.msg}"
        if e.act_val > e.exp_val and (0 < (e.act_val - e.exp_val) < 2):
            return (msg, "newWord", e.exp_val, word_path, word_path)
        else:
            return (msg, "replaceStr", word_path, "<all>", e.exp_val)

    def write_fixes(self, doc, errors):
        def get_page_str(page):
            p = f"> Page {page.page_idx}"
            ms = [f"{m.num_val}-{m.word_idx}" for m in page.num_markers]
            return f'{p} [{", ".join(ms)}]'

        config_file = self.conf_dir / f"{doc.pdf_name}.{self.conf_stub}.yml"
        if config_file.exists():
            return

        fixes = [self.get_fix(error) for error in errors]

        page_strs = [get_page_str(page) for page in doc.pages]

        nl = "\n# "
        pgs = f"# {nl.join(page_strs)}"
        msgs = f"# {nl.join(f[0] for f in fixes)}"
        edits = [f" - {f[1]} {f[2]} {f[3]} {f[3]}" for f in fixes]
        config_file.write_text(f"{pgs}\n\n{msgs}\n\n#edits:\n# {nl.join(edits)}")

    def test(self, doc, num_type):
        errors, exp_val = [], 1
        mIter = [(i, m, p) for p in doc.pages for (i, m) in enumerate(p.num_markers)]
        for (m_idx, marker, page) in mIter:
            if marker.num_type != num_type:
                continue

            if marker.num_val != exp_val and marker.num_val != 1:
                word_idx = marker.words[0].word_idx
                path = f"pa{page.page_idx}.nu{m_idx}"
                msg = f"Expected: {exp_val} Actual: {marker.num_val} word_idx: {word_idx}"
                err = MarkerMisalginedError(
                    path=path,
                    msg=msg,
                    exp_val=exp_val,
                    act_val=marker.num_val,
                    word_idx=word_idx,
                )
                exp_val = marker.num_val
                # marker.errors.append(err)
                errors.append(err)

            exp_val = 1 if marker.num_val == 1 else exp_val
            exp_val += 1
        return errors

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"num_marker: {doc.pdf_name}")

        doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)

        old_x_range = self.x_range
        old_min_marker = self.min_marker
        old_include_zero = self.include_zero

        self.x_range = doc_config.get("x_range", self.x_range)
        self.min_marker = doc_config.get("min_marker", self.min_marker)
        self.include_zero = doc_config.get("include_zero", self.include_zero)

        print(f"INCLUDE ZERO: {self.include_zero}")

        edits = doc_config.get("edits", [])
        if edits:
            print(f"Edited document: {doc.pdf_name}")
            doc.edit(edits)

        ignore_dict = doc_config.get("ignores", {})
        if ignore_dict:
            print(f"Ignoring {ignore_dict.keys()}")

        doc.add_extra_page_field("num_markers", ("list", __name__, "NumMarker"))
        for page in doc.pages:
            self.lgr.debug(f"< Page {page.page_idx}")

            if self.page_idxs:
                if page.page_idx not in self.page_idxs:
                    page.num_markers = []
                    self.lgr.debug("\tSkipping")
                    continue

            # TODO fix this, current good for debugging, bad for efficiency
            markers = [self.build_marker(w) for w in page.words]
            z_pgmks = zip(page.words, markers)
            num_markers = [m for (w, m) in z_pgmks if self.is_valid(page, w, m)]

            if len(num_markers) < self.min_marker:
                page.num_markers = []
                self.lgr.info(f"> Page {page.page_idx} [] *ignoring {len(num_markers)}")
                continue

            num_markers.sort(key=lambda m: m.ymin)
            [m.set_idx(idx) for idx, m in enumerate(num_markers)]
            page.num_markers = num_markers
            self.lgr.info(f"> Page {page.page_idx} {[str(m) for m in num_markers]}")

        errors = list(chain(*[self.test(doc, num_type) for num_type in NumType]))

        errors = [e for e in errors if not DataError.ignore_error(e, ignore_dict)]

        total_markers = sum(len(page.num_markers) for page in doc.pages)

        doc_stub = f"{doc.pdf_name}.{self.conf_stub}"

        # self.lgr.info(f'##{doc_stub} page doc.pages num_marker {total_markers} edits {len(edits)}'
        self.lgr.info(f"=={doc_stub} {total_markers} {DataError.error_counts(errors)}")
        [self.lgr.info(str(e)) for e in errors]

        # self.write_fixes(doc, errors)

        self.x_range = old_x_range
        self.min_marker = old_min_marker
        self.include_zero = old_include_zero

        self.remove_log_handler(doc)
        return doc
