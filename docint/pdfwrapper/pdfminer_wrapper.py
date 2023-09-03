import builtins
import ctypes
import re
from collections import Counter
from operator import itemgetter, attrgetter
from pathlib import Path
from itertools import groupby
import functools

import pdfminer
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTChar, LTTextBox, LTTextLine, LTFigure
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser

from docint.pdfwrapper import pdf

DEFAULT_X_TOLERANCE = 3
DEFAULT_Y_TOLERANCE = 3

EnglishFonts = [
    "andalus",
    "arial",
    "bahnschrift",
    "bitstreamcharter",
    "bookman",
    "calibri",
    "cambria",
    "comic",
    "courier",
    "gabriola",
    "garamond",
    "georgia",
    "gothic",
    "helvetica",
    "liberation",
    "marlett",
    "microsoftsansserif",
    "mincho",
    "myriadpro",
    "symbol",
    "tahoma",
    "timesbold",
    "timesnewroman",
    "timesroman",
    "trebuchet",
    "verdana",
    "wingdings",
    "timesitalic",
]


class CIDWord(pdf.CIDWord):
    def __init__(self, cids, rect, fonts):
        self._cids = cids
        self._rect = rect
        self._fonts = [f.replace("\x00", "") for f in fonts]

    @property
    def cids(self):
        return self._cids

    @property
    def bounding_box(self):
        return self._rect

    @property
    def fonts(self):
        return self._fonts

    @property
    def is_bold(self):
        return "bold" in self._font_name.lower()

    @property
    def is_italics(self):
        return "italics" in self._font_name.lower()


class Page(pdf.Page):
    def __init__(self, page_idx, page_impl, pdf):
        self.page_idx = page_idx
        self.page_impl = page_impl
        self.pdf = pdf
        self._cid_words = None

    @property
    def width(self):
        raise NotImplementedError("implement width")

    @property
    def height(self):
        raise NotImplementedError("implement width")

    @property
    def words(self):
        raise NotImplementedError("implement width")

    @property
    def chars(self):
        raise NotImplementedError("implement width")

    @property
    def images(self):
        raise NotImplementedError("implement width")

    @property
    def rotation(self):
        raise NotImplementedError("implement width")

    def page_image_to_pil(self, *, dpi=None):
        raise NotImplementedError("implement width")

    def page_image_save(self, file_path, *, dpi=None):
        pass

    def build_words(self):
        def build_char(c):
            return {
                "text": int(c._text[5:].strip(")"))
                if c._text[:5] == "(cid:"
                else c._text,  # text would be cid:(123)
                "fontname": clean_fontname(c.fontname),
                "bbox": [c.x0, height - c.y1, c.x1, height - c.y0],
                "size": c.size,
                "upright": c.upright,
            }

        def merge_chars(line_chars, line_idx):
            def char_isspace(c):
                t = c["text"]
                return t == 3 if isinstance(t, int) else t.isspace()

            # if line_idx == 7:
            #     import pdb
            #     pdb.set_trace()

            def xmid(c):
                return (c["bbox"][0] + c["bbox"][2]) / 2.0

            # line_chars.sort(key=itemgetter('bbox'))
            line_chars.sort(key=xmid)

            print("Done sorting")
            return [list(g) for (k, g) in groupby(line_chars, key=char_isspace) if not k]

        def build_line_words(line_word_chars):
            words = []
            for word_chars in line_word_chars:
                if not word_chars:
                    continue

                cids = [c["text"] for c in word_chars]
                xmin, xmax = word_chars[0]["bbox"][0], word_chars[-1]["bbox"][2]

                ymin = min(w["bbox"][1] for w in word_chars)
                ymax = max(w["bbox"][3] for w in word_chars)

                rect = [xmin, ymin, xmax, ymax]
                fonts = [c["fontname"] for c in word_chars]

                words.append(CIDWord(cids, rect, fonts))
            return words

        def get_LTChars(objs):
            chars = []
            for obj in objs:
                if isinstance(obj, LTChar):
                    chars.append(obj)
                elif hasattr(obj, "_objs"):
                    chars.extend(get_LTChars(obj._objs))
            return chars

        def cluster_chars_inlines(lt_chars):
            lt_chars.sort(key=attrgetter("y0"))

            def group_chars_inline(lines, lt_char):
                if not lines:
                    return [[lt_char]]

                last_line, last_char = lines[-1], lines[-1][-1]
                if (lt_char.y0 - last_char.y0) > DEFAULT_Y_TOLERANCE:
                    lines.append([lt_char])
                else:
                    last_line.append(lt_char)
                return lines

            lines = functools.reduce(group_chars_inline, lt_chars, [])
            return lines

        self.pdf.interpreter.process_page(self.page_impl)
        layout = self.pdf.device.get_result()

        height = layout.height

        lt_chars = get_LTChars(layout._objs)
        lt_lines = cluster_chars_inlines(lt_chars)

        self._cid_words = []
        for line_idx, lt_line in enumerate(reversed(lt_lines)):
            line_chars = [build_char(c) for c in lt_line]
            line_word_chars = merge_chars(line_chars, line_idx)
            line_words = build_line_words(line_word_chars)
            self._cid_words.extend(line_words)

        # for box in get_LTTextBoxes(layout._objs):
        #     for line in (ln for ln in box._objs if isinstance(ln, LTTextLine)):
        #         line_chars = [ build_char(c) for c in line._objs if isinstance(c, LTChar)]
        #         line_chars = [ c for c in line_chars if c['text']]
        #         line_word_chars = merge_chars(line_chars)
        #         line_words = build_line_words(line_word_chars)
        #         self._cid_words.extend(line_words)

    @property
    def cid_words(self):
        if not self._cid_words:
            self.build_words()
        return self._cid_words


def open(file_or_buffer, password=None):
    return PDF(file_or_buffer, password)


def clean_fontname(f):
    if "+" in f:
        _, f = f.split("+", 1)
    f = f.replace(" ", "").replace("-", "").replace(",", "").replace("\x00", "").lower().strip()
    return f


class PDF(pdf.PDF):
    def __init__(self, file_or_buffer, password=None):
        if isinstance(file_or_buffer, str):
            pdf_path = file_or_buffer
        elif isinstance(file_or_buffer, Path):
            pdf_path = str(file_or_buffer)
        else:
            raise NotImplementedError("Incorrect input {type(file_or_buffer)}")

        fp = builtins.open(pdf_path, "rb")
        parser = PDFParser(fp)
        self.document = PDFDocument(parser, password="")

        if not self.document.is_extractable:
            raise "Not extractable"

        class MyPDFResourceManager(PDFResourceManager):
            def get_font(self, objid, spec):
                font = super().get_font(objid, spec)
                font_name = clean_fontname(font.fontname)
                print(f"Processing font: {font_name}")
                if font_name in EnglishFonts:
                    print(f"\tReturning: {font_name}")
                    return font

                if hasattr(font, "unicode_map") and not isinstance(font.unicode_map, dict):
                    if font.unicode_map is not None:
                        print(f"\tDeleting unicode map: {font_name}")
                        font.unicode_map = {}  # remove the unicode so that we only get cids
                return font

        def createDeviceInterpreter():
            rsrcmgr = MyPDFResourceManager()
            laparams = LAParams()
            device = PDFPageAggregator(rsrcmgr, laparams=laparams)
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            return device, interpreter

        self.device, self.interpreter = createDeviceInterpreter()
        pdfminer_pages = PDFPage.create_pages(self.document)
        self._pages = [Page(i, p, self) for (i, p) in enumerate(pdfminer_pages)]

    @property
    def pages(self):
        return self._pages


if __name__ == "__main__":
    import sys
    from docint import pdfwrapper

    for file_path in sys.argv[1:]:
        pdf_path = Path(file_path)
        try:
            pdf = pdfwrapper.open(pdf_path, library_name="pdfminer")
            for (page_idx, page) in enumerate(pdf.pages):
                if page_idx > 2:
                    continue

                print(f"Page: {page_idx} # CIDWords: {len(page.cid_words)}")
                # for cid_word in page.cid_words:
                #     print('\t' + ''.join(cid_word.cids) + '\t' + ','.join(f[:2] for f in cid_word.fonts))

        except Exception as e:
            sys.stdin.write(f"Exception: {pdf_path.name:20s} {e}\n")
