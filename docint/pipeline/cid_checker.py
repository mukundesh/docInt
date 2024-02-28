import base64
import copy
import math
import re
from pathlib import Path

import BytesIO
import yaml
from PIL import Image

from .. import pdfwrapper
from ..page import Page
from ..pdfwrapper.pdfminer_wrapper import EnglishFonts
from ..shape import Box, Coord, Poly, Shape, doc_to_image
from ..vision import Vision
from ..word import BreakType, Word

# This componet creates an html file with cids and images
# As far as I could read it only shows which words have cid: embedded in them


@Vision.factory(
    "cid_checker",
    default_config={
        "stub": "cid_checker",
        "output_dir": "output/html",
    },
)
class CIDChecker:
    def __init__(self, stub, output_dir):
        self.stub = stub
        self.output_dir = Path(output_dir)

    def get_page_image_path(self, page):
        image_path = self.image_dir / f"{page.doc.pdf_name}-{page.page_idx+1}.png"

        if not image_path.exists():
            pdf = pdfwrapper.open(page.doc.pdf_path, library_name="pypdfium2")
            image_width, image_height = pdf.pages[page.page_idx].page_image_save(image_path)
        return image_path

    def get_word_base64_image(self, word):
        image_path = self.get_page_image_path(word.page_idx)

        with Image.open(image_path) as img:
            top, bot = word.box.top, word.box.bot
            img_top, img_bot = doc_to_image(top), doc_to_image(bot)
            crop_box = [img_top.x, img_top.y, img_bot.x, img_bot.y]

            cropped_img = img.crop(crop_box)
            buffered = BytesIO()
            cropped_img.save(buffered, format="PNG")

        return base64.b64encode(buffered.getvalue()).decode("utf-8")

    def get_missing_cid_words(page):
        missing_cid_words = [w for w in page.words if "(cid:" in w.text]

        font_missing_cid_dict = {}

        for m_word in missing_cid_words:
            font_cids = re.findall(r"([a-zA-Z]+)-cid:(\d+)", m_word.text)

            for font, cid in font_cids:
                font_missing_cid_dict.setdefault(font, {}).setdefault(int(cid), []).append(m_word)

        return font_missing_cid_dict

    def get_row(self, cid, missing_words):
        word = missing_words[0]
        cids = word.page.cid_words[word.word_idx].cids

        word_path = f"pa{word.page.page_idx}.wo{word.word_idx}"
        img_data = self.get_word_base64_image(word)
        img = f'<img src="data:image/<file-extension>;base64,{img_data}" alt="{word_path}">'

        row = [str(cid), ",".join(str(c) for c in cids), img]

        row_str = f'<tr><td>{row[0]}</td><td>{row[1]}</td><td height="100">{row[2]}</td></tr>'
        return row_str

    def write_table(self, doc, rows):
        html_path = self.output_dir / f"{doc.pdf_name}.html"
        rows_str = "\n".join(rows)

        html_path.write(f"<table>{rows_str}</table>")

    def __call__(self, doc):
        rows = []
        for page in doc.pages:
            if not page.cid_words:
                continue

            font_missing_cid_dict = self.get_missing_cid_words(page)
            for font, missing_cid_dict in font_missing_cid_dict.items():
                sorted_cids = sorted(missing_cid_dict.values())
                rows += [self.get_row(cid, missing_cid_dict[cid]) for cid in sorted_cids]

        self.write_html(font, rows)
        return doc
