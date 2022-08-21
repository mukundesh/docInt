import pdfplumber

from ..page import Page
from ..shape import Box, Coord
from ..vision import Vision
from ..word import BreakType, Word


@Vision.factory(
    "pdf_reader",
    default_config={
        "x_tol": 1,
        "y_tol": 1,
    },
)
class PDFReader:
    def __init__(self, x_tol, y_tol):
        self.x_tol = x_tol
        self.y_tol = y_tol

    def build_word(self, doc, page_idx, word_idx, pdf_page, pdf_word):
        x0, x1 = pdf_word["x0"] / pdf_page.width, pdf_word["x1"] / pdf_page.width
        y0, y1 = pdf_word["top"] / pdf_page.height, pdf_word["bottom"] / pdf_page.height

        box = Box(top=Coord(x=x0, y=y0), bot=Coord(x=x1, y=y1))
        text = pdf_word["text"]
        return Word(
            doc=doc,
            page_idx=page_idx,
            word_idx=word_idx,
            text_=text,
            break_type=BreakType.Space,
            shape_=box,
        )

    def __call__(self, doc):
        pdf = pdfplumber.open(doc.pdf_path)

        for page_idx, pdf_page in enumerate(pdf.pages):
            pdf_page = pdf_page.dedupe_chars(tolerance=1)

            pdf_words = pdf_page.extract_words(x_tolerance=self.x_tol, y_tolerance=self.y_tol)
            pdf_words = [p_word for p_word in pdf_words if p_word["text"]]

            words = [
                self.build_word(doc, page_idx, idx, pdf_page, pdf_word) for (idx, pdf_word) in enumerate(pdf_words)
            ]

            page = Page(
                doc=doc,
                page_idx=page_idx,
                words=words,
                width_=pdf_page.width,
                height_=pdf_page.height,
            )
            doc.pages.append(page)
        return doc
