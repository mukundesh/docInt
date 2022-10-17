from .. import pdfwrapper
from ..page import Page
from ..shape import Shape
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

    def __call__(self, doc):
        def to_doc_coords(bbox, page):
            x0, y0, x1, y1 = bbox
            return [
                x0 / page.width,
                y0 / page.height,
                x1 / page.width,
                y1 / page.height,
            ]

        def build_word(word, word_idx, page):
            doc_bbox = to_doc_coords(word.bounding_box, page)
            box = Shape.build_box(doc_bbox)
            return Word(
                doc=doc,
                page_idx=page_idx,
                word_idx=word_idx,
                text_=word.text,
                break_type=BreakType.Space,
                shape_=box,
            )

        pdf = pdfwrapper.open(doc.pdf_path)
        for page_idx, pdf_page in enumerate(pdf.pages):
            words = [build_word(w, idx, pdf_page) for (idx, w) in enumerate(pdf_page.words)]
            page = Page(
                doc=doc,
                page_idx=page_idx,
                words=words,
                width_=pdf_page.width,
                height_=pdf_page.height,
            )
            doc.pages.append(page)
        return doc
