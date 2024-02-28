import tempfile
from itertools import groupby
from operator import itemgetter
from pathlib import Path

from more_itertools import first

from ..doc import Doc
from ..pdfwrapper import open as pdf_open
from ..region import Region
from ..shape import Box
from ..vision import Vision
from ..word import BreakType, Word


def build_word(page, word_idx, text, bbox, break_type):
    shape = Box.from_bounding_box(bbox)
    return Word(
        doc=page.doc,
        page_idx=page.page_idx,
        word_idx=word_idx,
        text_=text,
        break_type=break_type,
        shape_=shape,
    )


def add_words_to_page(page, pdf_page, languages):
    import pytesseract

    lang_str = "+".join(languages)

    with tempfile.NamedTemporaryFile(suffix=".png") as temp_file_obj:
        img_width, img_height = pdf_page.page_image_save(temp_file_obj.name, dpi=600)
        tess_data = pytesseract.image_to_data(
            temp_file_obj.name,
            lang=lang_str,
            output_type="dict",
            config="-c preserve_interword_spaces=1",
        )

    info_iter = zip(*[tess_data[k] for k in "text-left-top-width-height-conf".split("-")])
    word_idx, tess_page_words = 0, []
    for idx, (text, lft, top, w, h, conf) in enumerate(info_iter):
        if not text:
            tess_page_words.append(None)
            continue

        x0, y0 = lft / img_width, top / img_height
        x1, y1 = x0 + w / img_width, y0 + h / img_height

        word = build_word(page, word_idx, text, [x0, y0, x1, y1], BreakType.Space)
        if word.text == " " and word.box.width > 0.2:
            tess_page_words.append(None)
        else:
            page.words.append(word)
            tess_page_words.append(word)
            word_idx += 1


@Vision.factory(
    "tess_recognizer2",
    depends=["pytesseract", "apt:tesseract-ocr-all"],
    is_recognizer=True,
    default_config={
        "output_dir_path": "output",
        "output_stub": "doc",
        "compress_output": False,
        "languages": ["eng"],
    },
)
class TesseractRecognizer2:
    def __init__(self, output_dir_path, output_stub, compress_output, languages):
        self.output_dir_path = Path(output_dir_path)
        self.output_stub = output_stub
        self.compress_output = compress_output
        self.languages = languages

    def __call__(self, doc):
        print(f"Processing {doc.pdf_name}")

        json_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"
        if json_path.exists():
            doc = Doc.from_disk(json_path)
            doc.pipe_names[:-1] = []
            return doc

        pdf = pdf_open(doc.pdf_path, library_name="pypdfium2")

        for page, pdf_page in zip(doc.pages, pdf.pages):
            add_words_to_page(page, pdf_page, self.languages)

        # line_numbers are defined only inside a block, they start from 0 for every block
        # need to define page_level line_numbers, storing prev_block_line number t

        # Commenting this line number logic as if two blocks are horizontaally adjasecent
        # then line numbering can get confusing.

        # Look at git history to get the code for line finding.

        # Also because our empty line has no words,it has no shape, makeing it difficult
        # to sort a list of lines

        doc.to_disk(json_path)
        return doc
