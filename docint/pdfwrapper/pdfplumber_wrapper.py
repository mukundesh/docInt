import io

import pdfplumber
import PIL.Image

from docint.pdfwrapper import pdf


def open(file_or_buffer, password=None):
    return PDF(file_or_buffer)


class Word(pdf.Word):
    def __init__(self, word):
        self._word = word

    @property
    def text(self):
        return self._word['text']

    @property
    def bounding_box(self):
        x0, x1 = float(self._word["x0"]), float(self._word["x1"])
        y0, y1 = float(self._word["top"]), float(self._word["bottom"])
        return (x0, y0, x1, y1)


class Image(pdf.Image):
    def __init__(self, image):
        self._image = image

    @property
    def width(self):
        return self._image['srcsize'][0]

    @property
    def height(self):
        return self._image['srcsize'][1]

    @property
    def size(self):
        return (self.width, self.height)

    @property
    def width_resolution(self):
        raise NotImplementedError('width_resolution is not available')

    @property
    def height_resolution(self):
        raise NotImplementedError('width_resolution is not available')

    @property
    def bounding_box(self):
        fields = ['x0', 'top', 'x1', 'bottom']
        return [float(self._image[f]) for f in fields]

    @property
    def get_image_type(self):
        pass

    def write(file_path):
        raise NotImplementedError('implement width')

    def to_pil(self):
        def _getPILMode(colorspace, bitsPerComponent):
            if colorspace == 'DeviceRGB':
                return 'RGB'
            elif colorspace == 'DeviceGray':
                return '1'
            else:  # TODO Please check colorspace option in pdf
                return '1'

        pdfStream = self._image['stream']
        if 'Filter' in pdfStream and pdfStream['Filter'].name == 'DCTDecode':
            image = PIL.Image.open(io.BytesIO(pdfStream.get_data()))
        else:
            mode = _getPILMode(pdfStream['ColorSpace'], self._image['bits'])
            image = PIL.Image.frombytes(mode, self.size, pdfStream.get_data())
        return image


class Page(pdf.Page):
    def __init__(self, page):
        self._page = page
        self._page.dedupe_chars(tolerance=1)
        self._words = [Word(w) for w in self._page.extract_words() if w['text']]
        self._images = [Image(i) for i in self._page.images]

    @property
    def width(self):
        return self._page.width

    @property
    def height(self):
        return self._page.height

    @property
    def words(self):
        return self._words

    @property
    def images(self):
        return self._images

    @property
    def page_image(self):
        if self.has_page_image():
            return Image(self._images[0])
        else:
            w_res = max(i.width_resolution for i in self._images)
            h_res = max(i.height_resolution for i in self._images)
            res = max(w_res, h_res)
            return self._page.to_image(resolution=res)


class PDF(pdf.PDF):
    def __init__(self, file_or_buffer, password=None):
        self._pdf = pdfplumber.open(file_or_buffer, password)
        self._pages = [Page(p) for p in self._pdf.pages]

    @property
    def pages(self):
        return self._pages
