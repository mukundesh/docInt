import ctypes
import re
from pathlib import Path

import PIL.Image
import pypdfium2 as pdfium

from docint.pdfwrapper import pdf

DEFAULT_DPI = 72

COLORSPACE_FAMILY = {
    0: "FPDF_COLORSPACE_UNKNOWN",
    1: "FPDF_COLORSPACE_DEVICEGRAY",
    2: "FPDF_COLORSPACE_DEVICERGB",
    3: "FPDF_COLORSPACE_DEVICECMYK",
    4: "FPDF_COLORSPACE_CALGRAY",
    5: "FPDF_COLORSPACE_CALRGB",
    6: "FPDF_COLORSPACE_LAB",
    7: "FPDF_COLORSPACE_ICCBASED",
    8: "FPDF_COLORSPACE_SEPARATION",
    9: "FPDF_COLORSPACE_DEVICEN",
    10: "FPDF_COLORSPACE_INDEXED",
    11: "FPDF_COLORSPACE_PATTERN",
}


def open(file_or_buffer, password=None):
    return PDF(file_or_buffer)


class Char(pdf.Char):
    def __init__(self, text, rect):
        self._text = text
        self._rect = rect

    @property
    def text(self):
        return self._text

    @property
    def bounding_box(self):
        return self._rect


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
    def horizontal_dpi(self):
        return self._metadata.horizontal_dpi

    @property
    def vertical_dpi(self):
        return self._metadata.vertical_dpi

    @property
    def bits_per_pixel(self):
        return self._metadata.bits_per_pixel

    @property
    def colorspace_int(self):
        return self._metadata.colorspace

    @property
    def colorspace_str(self):
        return COLORSPACE_FAMILY[int(self._metadata.colorspace)]

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
            bits_per_pixel = self._metadata.bits_per_pixel
            print(f"BPP {bits_per_pixel}")
            buffer = ctypes.cast(
                buffer_start,
                ctypes.POINTER(ctypes.c_ubyte * (self.width * self.height * 3)),
            )
            # if bits_per_pixel == 24:
            self._pil_image = PIL.Image.frombuffer(
                "RGB", (self.width, self.height), buffer.contents, "raw", "RGB", 0, 1
            )
            # elif bits_per_pixel == 1:
            #    self._pil_image = PIL.Image.frombuffer(
            #        "1", (self.width, self.height), buffer.contents, "raw", "1", 0, 1
            #    )
            # else:
            #    raise NotImplementedError(f'Unable to handle bpp = {bits_per_pixel}')
            return self._pil_image

    def extract_image(self, file_path):
        def modulo_expand(size):
            pixels = size[0] * size[1]
            modulo = pixels % 8
            return pixels if modulo == 0 else pixels + 8 - modulo

        # TODO expand this, currently only works if bits_per_pixel == 1
        buf_len = pdfium.FPDFImageObj_GetImageDataDecoded(self.lib_image.raw, None, 0)
        assert buf_len * 8 == modulo_expand(self.size)

        buffer = ctypes.create_string_buffer(buf_len)
        pdfium.FPDFImageObj_GetImageDataDecoded(self.lib_image.raw, buffer, buf_len)

        print(buf_len)

        b = bytes(buffer)
        print(len(b))

        pil_image = PIL.Image.frombytes("1", self.size, b)
        pil_image.save(file_path)
        return pil_image.size

    def save(self, file_path):
        self.to_pil().save(file_path)

    def get_filters(self):
        filters = []
        num_filters = pdfium.FPDFImageObj_GetImageFilterCount(self.lib_image.raw)
        for idx in range(num_filters):
            buf_len = pdfium.FPDFImageObj_GetImageFilter(self.lib_image.raw, idx, None, 0)
            buffer = ctypes.create_string_buffer(buf_len)
            pdfium.FPDFImageObj_GetImageFilter(self.lib_image.raw, idx, buffer, buf_len)
            filter = "".join(chr(i) for i in bytes(buffer)).rstrip("\x00")
            filters.append(filter)
        return filters


class Page(pdf.Page):
    def __init__(self, page, page_idx):
        self.lib_page = page
        self.page_idx = page_idx
        self._words = None
        self._chars = None
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
            return "|".join(",".join(f"{c:.1f}" for c in rect) for rect in rects)

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
            return "|".join(get_text(r) for r in rects)

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
        assert count_chars == len(
            page_text
        ), f"count_chars mismatch {count_chars} {len(page_text)}\n{page_text}"

        words = []
        page_text = page_text.replace(chr(65534), " ")
        for match in re.finditer(r"\S+", page_text):
            (s_index, e_index), text = match.span(), match.group()
            rects = list(lib_textpage.get_rectboxes(s_index, e_index - s_index))
            rect = merge_rects(rects) if len(rects) > 1 else rects[0]
            if len(rects) > 1:
                rect_text = get_text(rect).strip()  # noqa
                char_text = get_chars(s_index, e_index)  # noqa
                # assert (
                #    text == rect_text
                # ), f"MERGED: {self.page_idx}[{s_index}:{e_index}] {text} + {to_texts(rects)} -> {rect_text} char: {char_text}\n{to_str(rects)}\n{to_str([rect])}"

            x0, y0, x1, y1 = rect
            # print(text, [x0, y0, x1, y1])
            if self.rotation == 90:
                bottom, top = y1, y0
                top, x0 = x0, top
                bottom, x1 = x1, bottom
            else:
                bottom, top = self.height - y0, self.height - y1
            words.append(Word(text, (x0, top, x1, bottom)))
        return words

    def build_chars(self, lib_textpage):
        page_text = lib_textpage.get_text_range()
        count_chars = lib_textpage.count_chars()
        assert count_chars == len(
            page_text
        ), f"count_chars mismatch {count_chars} {len(page_text)}\n{page_text}"

        chars = []
        for (char_idx, char_text) in enumerate(page_text):
            char_rect = lib_textpage.get_charbox(char_idx)
            x0, y0, x1, y1 = char_rect
            if self.rotation == 90:
                bottom, top = y1, y0
                top, x0 = x0, top
                bottom, x1 = x1, bottom
            else:
                bottom, top = self.height - y0, self.height - y1
            char_rect = (x0, top, x1, bottom)
            chars.append(Char(char_text, char_rect))
        return chars

    @property
    def width(self):
        return self.lib_page.get_width()

    @property
    def height(self):
        return self.lib_page.get_height()

    @property
    def words(self):
        if self._words is None:
            self._words = self.build_words(self.lib_page.get_textpage())
        return self._words

    @property
    def chars(self):
        if self._chars is None:
            self._chars = self.build_chars(self.lib_page.get_textpage())
        return self._chars

    @property
    def images(self):
        return self._images

    @property
    def rotation(self):
        return self.lib_page.get_rotation()

    def page_image_to_pil(self, *, dpi=None):
        dpi = DEFAULT_DPI if dpi is None else dpi
        h_dpi = max((i.horizontal_dpi for i in self._images), default=dpi)
        v_dpi = max((i.vertical_dpi for i in self._images), default=dpi)
        max_dpi = max(h_dpi, v_dpi)
        return self.lib_page.render_to(pdfium.BitmapConv.pil_image, scale=max_dpi / 72.0)

    def page_image_save(self, file_path, *, dpi=None):
        page_image = self.page_image_to_pil(dpi=dpi)
        (width, height) = page_image.size
        page_image.save(file_path)
        return (width, height)


class PDF(pdf.PDF):
    def __init__(self, file_or_buffer, password=None):
        if isinstance(file_or_buffer, str):
            pdf_path = file_or_buffer
        elif isinstance(file_or_buffer, Path):
            pdf_path = str(file_or_buffer)
        else:
            raise NotImplementedError("Incorrect input {type(file_or_buffer)}")

        self.lib_pdf = pdfium.PdfDocument(pdf_path)
        self._pages = [Page(p, idx) for idx, p in enumerate(self.lib_pdf)]

    @property
    def pages(self):
        return self._pages

    def del_page(self, page_idx):
        self.lib_pdf.del_page(page_idx)

    def save(self, new_path):
        import builtins

        with builtins.open(new_path, "wb") as n:
            self.lib_pdf.save(n)


#     #print(f'Multiple rects {len(rects)} >{text}< {to_texts(rects)}')
#     merged_text = ''.join(get_text(r) for r in rects).strip()
#     if text != merged_text and ('/' not in merged_text) and ('-' not in merged_text):
#         #non_ascii = '|'.join(c for c in text if not c.isascii())
#         #num = ord(non_ascii) if non_ascii else 0
#         non_ascii, num = '',0
#         print(f'FAILED - {self.page_idx}[{s_index}:{e_index}] Multiple rects {len(rects)} >{text}< >{merged_text}< >{non_ascii}< ={num}= {to_texts(rects)}')
# #assert len(rects) == 1, f'Multiple rects {len(rects)} >{text}< {to_texts(rects)}'
