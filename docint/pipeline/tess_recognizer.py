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


@Vision.factory(
    "tess_recognizer",
    depends=["pytesseract", "apt:tesseract-ocr-all"],
    is_recognizer=True,
    default_config={
        "output_dir_path": "output",
        "output_stub": "doc",
        "compress_output": False,
        "languages": ["eng"],
    },
)
class TesseractRecognizer:
    def __init__(self, output_dir_path, output_stub, compress_output, languages):
        self.output_dir_path = Path(output_dir_path)
        self.output_stub = output_stub
        self.compress_output = compress_output
        self.languages = languages

    def build_word(self, page, word_idx, text, bbox, break_type):
        shape = Box.from_bounding_box(bbox)
        return Word(
            doc=page.doc,
            page_idx=page.page_idx,
            word_idx=word_idx,
            text_=text,
            break_type=break_type,
            shape_=shape,
        )

    def build_lines(self, page, page_line_nums, tess_word_nums, page_words):
        zip_iter = zip(page_line_nums, tess_word_nums, page_words)

        lines = []
        for line_num, line_words in groupby(zip_iter, key=itemgetter(0)):  # groupby line_num
            line_words = sorted(line_words, key=itemgetter(1))  # groupby word_num
            line_page_words = [lw[2] for lw in line_words if lw[2]]

            lpw = line_page_words
            lines.append(Region.from_words(lpw) if lpw else Region.no_words(page.page_idx))
        return lines

    def __call__(self, doc):
        print(f"Processing {doc.pdf_name}")

        json_path = self.output_dir_path / f"{doc.pdf_name}.{self.output_stub}.json"
        if json_path.exists():
            doc = Doc.from_disk(json_path)
            doc.pipe_names[:-1] = []
            return doc

        pdf = pdf_open(doc.pdf_path, library_name="pypdfium2")
        temp_file = tempfile.mkstemp(suffix=".png")[1]

        import pytesseract

        lang_str = "+".join(self.languages)
        for page, pdf_page in zip(doc.pages, pdf.pages):
            img_width, img_height = pdf_page.page_image_save(temp_file, dpi=600)

            tess_data = pytesseract.image_to_data(temp_file, lang=lang_str, output_type="dict")
            info_iter = zip(*[tess_data[k] for k in "text-left-top-width-height-conf".split("-")])

            word_idx = 0
            tess_page_words = []
            for idx, (text, lft, top, w, h, conf) in enumerate(info_iter):
                if not text:
                    tess_page_words.append(None)
                    continue

                x0, y0 = lft / img_width, top / img_height
                x1, y1 = x0 + w / img_width, y0 + h / img_height

                word = self.build_word(page, word_idx, text, [x0, y0, x1, y1], BreakType.Space)
                page.words.append(word)
                tess_page_words.append(word)
                word_idx += 1

            # line_numbers are defined only inside a block, they start from 0 for every block
            # need to define page_level line_numbers, storing prev_block_line number t

            prev_block_lines = [None] * len(tess_data["line_num"])
            start_idx, total_prev_block_lines = 0, 0
            for block_num, blocks in groupby(tess_data["block_num"]):
                end_idx = start_idx + len(list(blocks))
                prev_block_lines[start_idx:end_idx] = [total_prev_block_lines] * (
                    end_idx - start_idx
                )

                total_prev_block_lines += max(tess_data["line_num"][start_idx:end_idx]) + 1
                start_idx = end_idx

            page_line_nums = [pl + bl for (pl, bl) in zip(prev_block_lines, tess_data["line_num"])]

            page.lines = self.build_lines(
                page, page_line_nums, tess_data["word_num"], tess_page_words
            )

        doc.to_disk(json_path)
        return doc
