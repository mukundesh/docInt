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
        return [x0, top, x1, bottom]

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
    def __init__(self, page):
        self.lib_page = page
        self._words = self.build_words(self.lib_page.get_textpage())
        img_type = pdfium.FPDF_PAGEOBJ_IMAGE
        self._images = [Image(o, self) for o in self.lib_page.get_objects() if o.type == img_type]

    def extract_text(self, lib_textpage):
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

    def build_words(self, lib_textpage):
        if self.lib_page.get_rotation() == 0:
            page_text = lib_textpage.get_text()
        else:
            page_text = self.extract_text(lib_textpage)

        count_chars = lib_textpage.count_chars()
        assert count_chars == len(page_text), f'count_chars mismatch {count_chars} {len(page_text)}\n{page_text}'

        words = []
        for match in re.finditer(r'\S+', page_text):
            (s_index, e_index), text = match.span(), match.group()
            rects = list(lib_textpage.get_rectboxes(s_index, e_index - s_index))
            assert len(rects) == 1, f'Multiple rects {len(rects)}'
            x0, y0, x1, y1 = rects[0]
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
        self._pages = [Page(p) for p in self.lib_pdf]

    @property
    def pages(self):
        return self._pages
