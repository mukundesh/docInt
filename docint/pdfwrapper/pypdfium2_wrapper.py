import ctypes
import re
from pathlib import Path

import PIL.Image
import pypdfium2 as pdfium

from docint.pdfwrapper import pdf


def open(file_or_buffer, password=None):
    return PDF(file_or_buffer)


class Word(pdf.Word):
    def __init__(self, text, rect):
        self._text = text
        self._rect = rect

    @property
    def text(self):
        return self._text

    @property
    def bounding_box(self):
        return self._rect


class Image(pdf.Image):
    def __init__(self, image_obj, page):
        self.lib_image = image_obj
        self.page = page
        self._metadata = pdfium.FPDF_IMAGEOBJ_METADATA()
        result = pdfium.FPDFImageObj_GetImageMetadata(
            self.lib_image.raw, page.lib_page.raw, ctypes.byref(self._metadata)
        )

        assert result
        self._pil_image = None

    @property
    def width(self):
        return self._metadata.width

    @property
    def height(self):
        return self._metadata.height

    @property
    def size(self):
        return (self.width, self.height)

    @property
    def width_resolution(self):
        return self._metadata.horizontal_dpi

    @property
    def height_resolution(self):
        return self._metadata.vertical_dpi

    @property
    def bounding_box(self):
        (x0, y0, x1, y1) = self.lib_image.get_pos()
        bottom, top = self.page.height - y0, self.page.height - y1
        # return list(self._image.get_pos())
        return (x0, top, x1, bottom)

    @property
    def get_image_type(self):
        pass

    def to_pil(self):
        if self._pil_image:
            return self._pil_image
        else:
            _bitmap = pdfium.FPDFImageObj_GetBitmap(self.lib_image.raw)
            buffer_start = pdfium.FPDFBitmap_GetBuffer(_bitmap)
            buffer = ctypes.cast(buffer_start, ctypes.POINTER(ctypes.c_ubyte * (self.width * self.height * 3)))
            self._pil_image = PIL.Image.frombuffer(
                "RGB", (self.width, self.height), buffer.contents, "raw", "RGB", 0, 1
            )
            return self._pil_image

    def write(self, file_path):
        self.to_pil().save(file_path)


class Page(pdf.Page):
    def __init__(self, page, page_idx):
        self.lib_page = page
        self.page_idx = page_idx
        self._words = self.build_words(self.lib_page.get_textpage())
        img_type = pdfium.FPDF_PAGEOBJ_IMAGE
        self._images = [Image(o, self) for o in self.lib_page.get_objects() if o.type == img_type]

    def extract_text_old(self, lib_textpage):
        left = top = 0
        right = self.height if self.lib_page.get_rotation() in (90, 270) else self.width
        bottom = self.width if self.lib_page.get_rotation() in (90, 270) else self.height

        args = (lib_textpage.raw, left, top, right, bottom)
        n_chars = pdfium.FPDFText_GetBoundedText(*args, None, 0)
        if n_chars <= 0:
            return ""
        n_bytes = 2 * n_chars
        buffer = ctypes.create_string_buffer(n_bytes)
        buffer_ptr = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort))
        pdfium.FPDFText_GetBoundedText(*args, buffer_ptr, n_chars)
        text = buffer.raw.decode("utf-16-le", errors="ignore")
        return text

    def extract_text(self, lib_textpage):
        return lib_textpage.get_text_range()

    def build_words(self, lib_textpage):
        def get_char(char_idx):
            buffer = ctypes.create_string_buffer(2 + 1)
            buffer_ptr = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort))
            pdfium.FPDFText_GetText(lib_textpage.raw, char_idx, 1, buffer_ptr)
            text = buffer.raw.decode("utf-16-le", errors="ignore")
            return text

        def get_chars(char_start, char_end):
            return "-".join(get_char(c) for c in range(char_start, char_end))

        def to_str(rects):
            return '|'.join(','.join(f'{c:.1f}' for c in rect) for rect in rects)

        def get_text(r):
            rect = r
            n_chars = pdfium.FPDFText_GetBoundedText(lib_textpage.raw, *rect, None, 0)
            if n_chars <= 0:
                return ""
            n_bytes = 2 * n_chars
            buffer = ctypes.create_string_buffer(n_bytes)
            buffer_ptr = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ushort))
            pdfium.FPDFText_GetBoundedText(lib_textpage.raw, *rect, buffer_ptr, n_chars)
            text = buffer.raw.decode("utf-16-le", errors="ignore")
            return text

        def to_texts(rects):
            return '|'.join(get_text(r) for r in rects)

        def normalize(rect):
            (lft, bot, rgt, top) = rect
            (lft, rgt) = (rgt, lft) if lft > rgt else (lft, rgt)
            (top, bot) = (bot, top) if bot > top else (top, bot)
            return [lft, bot, rgt, top]

        def merge_rect(rect1, rect2):
            rect2 = normalize(rect2)
            lft = min(rect1[0], rect2[0])
            bot = min(rect1[1], rect2[1])
            rgt = max(rect1[2], rect2[2])
            top = max(rect1[3], rect2[3])
            return [lft, bot, rgt, top]

        def merge_rects(rects):
            rect = rects[0]
            for r in rects[1:]:
                rect = merge_rect(rect, r)
            return rect

        page_text = self.extract_text(lib_textpage)
        count_chars = lib_textpage.count_chars()
        assert count_chars == len(page_text), f'count_chars mismatch {count_chars} {len(page_text)}\n{page_text}'

        words = []
        page_text = page_text.replace(chr(65534), ' ')
        for match in re.finditer(r'\S+', page_text):
            (s_index, e_index), text = match.span(), match.group()
            rects = list(lib_textpage.get_rectboxes(s_index, e_index - s_index))
            rect = merge_rects(rects) if len(rects) > 1 else rects[0]
            if len(rects) > 1:
                rect_text = get_text(rect).strip()
                char_text = get_chars(s_index, e_index)
                assert (
                    text == rect_text
                ), f'MERGED: {self.page_idx}[{s_index}:{e_index}] {text} + {to_texts(rects)} -> {rect_text} char: {char_text}\n{to_str(rects)}\n{to_str([rect])}'

            x0, y0, x1, y1 = rect
            bottom, top = self.height - y0, self.height - y1
            words.append(Word(text, (x0, top, x1, bottom)))
        return words

    @property
    def width(self):
        return self.lib_page.get_width()

    @property
    def height(self):
        return self.lib_page.get_height()

    @property
    def words(self):
        return self._words

    @property
    def images(self):
        return self._images

    @property
    def rotation(self):
        return self.lib_page.get_rotation()

    @property
    def page_image(self):
        if self.has_one_large_image():
            return self._images[0]
        else:
            w_res = max(i.width_resolution for i in self._images)
            h_res = max(i.height_resolution for i in self._images)
            res = max(w_res, h_res)
            return self.lib_page.render_to(scale=res / 72.0)


class PDF(pdf.PDF):
    def __init__(self, file_or_buffer, password=None):
        if isinstance(file_or_buffer, str):
            pdf_path = file_or_buffer
        elif isinstance(file_or_buffer, Path):
            pdf_path = str(file_or_buffer)
        else:
            raise NotImplementedError('Incorrect input {type(file_or_buffer)}')

        self.lib_pdf = pdfium.PdfDocument(pdf_path)
        self._pages = [Page(p, idx) for idx, p in enumerate(self.lib_pdf)]

    @property
    def pages(self):
        return self._pages


#     #print(f'Multiple rects {len(rects)} >{text}< {to_texts(rects)}')
#     merged_text = ''.join(get_text(r) for r in rects).strip()
#     if text != merged_text and ('/' not in merged_text) and ('-' not in merged_text):
#         #non_ascii = '|'.join(c for c in text if not c.isascii())
#         #num = ord(non_ascii) if non_ascii else 0
#         non_ascii, num = '',0
#         print(f'FAILED - {self.page_idx}[{s_index}:{e_index}] Multiple rects {len(rects)} >{text}< >{merged_text}< >{non_ascii}< ={num}= {to_texts(rects)}')
# #assert len(rects) == 1, f'Multiple rects {len(rects)} >{text}< {to_texts(rects)}'
