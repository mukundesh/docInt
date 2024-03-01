import copy
import functools
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml
from more_itertools import first, pairwise
from pydantic import BaseModel

from .. import pdfwrapper
from ..doc import Doc
from ..page import Page
from ..shape import Box, Coord, Poly, Shape
from ..util import load_config
from ..vision import Vision
from ..word import BreakType, Word


def rev_enumerate(lst, start_idx):
    for idx, val in zip(range(start_idx - 1, -1, -1), lst[start_idx - 1 :: -1]):
        yield idx, val


# This component calculates info about words that are using CID fonts and stores them
# the info is useful to decide how to handle unknown fonts.


@Vision.factory(
    "pdf_cid_info",
    default_config={
        "stub": "cid_info",
        "output_dir": "output",
    },
)
class PDFCIDInfoReader:
    def __init__(self, stub, output_dir):
        self.output_dir = Path(output_dir)
        self.stub = stub
        self.conf_dir = Path("conf")

        self.font_cmap_dict = {}

    def get_cmap(self, font):
        if font in self.font_cmap_dict:
            return self.font_cmap_dict[font]

        yaml_file = self.cmaps_dir / f"{font}.yml"
        self.font_cmap_dict[font] = yaml.load(yaml_file.read_text(), Loader=yaml.FullLoader)
        return self.font_cmap_dict[font]

    def merge_word_cids(self, cid_words, page_idx):
        def is_mergeable(w1, w2):
            w1_xmax, w2_xmin = w1.bounding_box[2], w2.bounding_box[0]
            return (w2_xmin - w1_xmax < 2) and abs(w1.bounding_box[1] - w2.bounding_box[1]) < 1

        def merge_cid_words(w1, w2):
            w1.cids.extend(w2.cids)
            w1.fonts.extend(w2.fonts)
            wb1, wb2 = w1.bounding_box, w2.bounding_box
            wb1[0], wb1[1] = min(wb1[0], wb2[0]), min(wb1[1], wb2[1])
            wb1[2], wb1[3] = max(wb1[2], wb2[2]), max(wb1[3], wb2[3])

        word_idx = 0

        def merge_cids(res_cid_words, cid_word):
            nonlocal word_idx
            if not res_cid_words:
                res_cid_words.append(cid_word)

            elif is_mergeable(res_cid_words[-1], cid_word):
                # print(f'Merging page_idx:{page_idx} word_idx:{word_idx}')
                merge_cid_words(res_cid_words[-1], cid_word)
            else:
                res_cid_words.append(cid_word)

            word_idx += 1  # for debugging
            return res_cid_words

        return functools.reduce(merge_cids, cid_words, [])

    def __call__(self, doc):
        # print(f"> pdf_cid_info: {doc.pdf_name}")
        doc.add_extra_field("cid_info", ("noparse", "", ""))

        json_path = self.output_dir / f"{doc.pdf_name}.{self.stub}.json"
        if json_path.exists():
            doc.cid_info = json.loads(json_path.read_text())
            return doc

        pdf = pdfwrapper.open(doc.pdf_path, library_name="pdfminer")

        doc.cid_info = {"page_infos": [], "font_cmaps": {}}
        for pdf_page, page in zip(pdf.pages, doc.pages):
            page_cid_words = self.merge_word_cids(pdf_page.cid_words, page.page_idx)
            page_cid_info = {"multi_font_words": 0, "font_word_counts": {}}

            # sume of font_word_counts may be more than that number of words
            for page_cid_word in page_cid_words:
                fonts = set(page_cid_word.fonts)
                if len(fonts) > 1:
                    page_cid_info["multi_font_words"] += 1

                for font in fonts:
                    if font in page_cid_info["font_word_counts"]:
                        page_cid_info["font_word_counts"][font] += 1
                    else:
                        page_cid_info["font_word_counts"][font] = 0
            doc.cid_info["page_infos"].append(page_cid_info)

        for font, unicode_map in pdf.font_unicode_maps.items():
            doc.cid_info["font_cmaps"][font] = unicode_map.cid2unichr

        json_path.write_text(json.dumps(doc.cid_info))
        # print(f"< pdf_cid_info: {doc.pdf_name}")
        return doc
