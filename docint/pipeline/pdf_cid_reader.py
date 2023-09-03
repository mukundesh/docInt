import copy
import math
from pathlib import Path
from typing import Any, Dict, List
import re
import functools

from pydantic import BaseModel
from more_itertools import first, pairwise

from .. import pdfwrapper
from ..page import Page
from ..shape import Box, Coord, Poly, Shape
from ..vision import Vision
from ..word import BreakType, Word
from ..pdfwrapper.pdfminer_wrapper import EnglishFonts

import yaml


def rev_enumerate(lst, start_idx):
    for (idx, val) in zip(range(start_idx - 1, -1, -1), lst[start_idx - 1 :: -1]):
        yield idx, val


class WordInfo(BaseModel):
    cids: List[Any]
    fonts: List[str]

    def merge_info(self, info):
        self.cids.extend(info.cids)
        self.fonts.extend(info.fonts)


@Vision.factory(
    "pdf_cid_reader",
    default_config={
        "cmaps_dir": "conf/cmaps",
    },
)
class PDFCIDReader:
    def __init__(self, cmaps_dir):
        self.cmaps_dir = Path(cmaps_dir)
        self.font_cmap_dict = {}

    def get_cmap(self, font):
        if font in self.font_cmap_dict:
            return self.font_cmap_dict[font]

        yaml_file = self.cmaps_dir / f"{font}.yml"
        self.font_cmap_dict[font] = yaml.load(yaml_file.read_text(), Loader=yaml.FullLoader)
        return self.font_cmap_dict[font]

    def get_cid_str(self, info):
        cid_str_dict = {}
        for (font, cid) in zip(info.fonts, info.cids):
            if isinstance(cid, str):
                cid_str_dict[cid] = cid
            else:
                cmap = self.get_cmap(font)
                cid_char = cmap.get(cid, None)
                if cid_char:
                    cid_str_dict[cid] = cid_char
                else:
                    cid_str_dict[cid] = f"({font}-cid:{cid})"
        return str(cid_str_dict)

    def reorder_unicode(self, uni_str, start_idx=0):
        def is_unichr(c):
            ic = ord(c)
            return 2325 <= ic <= 2361

        def swap_right(s, r_idx, c):
            u_idx = first((idx for (idx, c) in enumerate(s[r_idx:]) if is_unichr(c)), None)
            u_idx += r_idx  # since we started the search from r_idx
            assert u_idx is not None, f"Error in {s}"
            return s[:r_idx] + s[r_idx + 1 : u_idx + 1] + c + s[u_idx + 1 :]

        def valid_r(s, idx):
            if s[idx] != "र":
                return True
            # if (idx != 0 and s[idx-1] == '्') or (idx < (len(s) -1) and s[idx + 1] == '्'):
            if idx != 0 and s[idx - 1] == "्":
                return False

            return True

        def swap_right2(s, r_idx, c):
            u_idxs = [
                idx for (idx, c) in enumerate(s[r_idx:]) if is_unichr(c) and valid_r(s, idx + r_idx)
            ]

            cutoff_idx = u_idxs[1] - 1 if len(u_idxs) > 1 else len(s[r_idx:]) - 1

            cutoff_idx += r_idx  # since we started the search from r_idx
            return s[:r_idx] + s[r_idx + 1 : cutoff_idx + 1] + c + s[cutoff_idx + 1 :]

        def swap_left(s, r_idx, c):
            u_idx = first((idx for (idx, c) in enumerate(s[r_idx::-1]) if is_unichr(c)), None)
            u_idx = r_idx - u_idx  #
            assert u_idx is not None, f"Error in {s}"
            return s[:u_idx] + c + s[u_idx:r_idx] + s[r_idx + 1 :]

        result = uni_str
        for match in re.finditer("ि", uni_str):
            r_idx = match.span()[0]
            if match.group() == "ि":
                result = swap_right2(result, r_idx, "ि")
            else:
                result = swap_left(result, r_idx, "ु")
        return result

    def is_unichr_cid(self, cid, font):
        if isinstance(cid, str):
            return False

        cmap = self.get_cmap(font)
        uc = cmap[cid]

        return False if not uc or len(uc) > 1 else 2325 <= ord(uc) <= 2361

    def reorder_cids(self, cids, fonts):
        rph_idxs = [idx for (idx, cid) in enumerate(cids) if cid == 91]

        result = cids[:]
        for rph_idx in rph_idxs:
            # u_idxs = [idx for (idx, cid) in enumerate(result[rph_idx::-1]) if self.is_unichr_cid(cid, fonts[rph_idx - idx])]
            # u_idx = rph_idx - u_idxs[-1]
            # result = result[:u_idx] + [cids[rph_idx]] + cids[u_idx:rph_idx] + cids[rph_idx+1:]
            result[rph_idx - 1], result[rph_idx] = result[rph_idx], result[rph_idx - 1]
        return result

    def reorder_cids2(self, w_cids, w_fonts):
        double_cids = {
            568: (91, 546),
            569: (91, 546),
            570: (91, 546),
            571: (91, 546),
            572: (91, 546),
            573: (91, 546),
            574: (91, 554),
            575: (91, 555),
            576: (91, 558),
            577: (91, 553),
            588: (91, 561),
            589: (91, 562),
        }

        result, fonts = w_cids[:], w_fonts[:]

        double_idxs = [idx for (idx, cid) in enumerate(result) if cid in double_cids]
        for (idx, double_idx) in enumerate(double_idxs):

            double_idx += idx  # as we are adding an extra character
            double_cid = result.pop(double_idx)

            assert double_cid in double_cids
            double_font = fonts.pop(double_idx)

            new_cids = double_cids[double_cid]

            for new_cid in reversed(new_cids):
                result.insert(double_idx, new_cid)
                fonts.insert(double_idx, double_font)

        rph_idxs = [idx for (idx, cid) in enumerate(result) if cid == 91]
        for rph_idx in rph_idxs:
            u_idxs = [
                idx
                for (idx, cid) in rev_enumerate(result, rph_idx)
                if self.is_unichr_cid(cid, fonts[idx])
            ]
            u_idx = u_idxs[0]
            rph = result.pop(rph_idx)
            result.insert(u_idx, rph)

        matra_cids = [464, 465, 466, 467, 468, 871, 872, 873, 874, 875, 876, 877, 878, 879]
        matra_idxs = [idx for (idx, cid) in enumerate(result) if cid in matra_cids]

        for matra_idx in matra_idxs:
            u_idxs = [
                idx
                for (idx, cid) in enumerate(result[matra_idx:], matra_idx)
                if self.is_unichr_cid(cid, fonts[idx])
            ]
            u_idx = u_idxs[0] if u_idxs else len(result)
            matra = result.pop(matra_idx)
            result.insert(u_idx, matra)

        return result, fonts

    def get_text(self, cid_word, word_idx):
        text = []
        # if word_idx in [271]:
        #     import pdb
        #     pdb.set_trace()

        # : क्र -> क ् र
        # : निर्ण -> न ि र ् ण
        # : पर्या -> प र ् य ा
        # : कार्य -> क ा र ् य

        # keep the original orders
        reordered_cids, reordered_fonts = self.reorder_cids2(cid_word.cids[:], cid_word.fonts)

        for (font, cid) in zip(reordered_fonts, reordered_cids):
            if isinstance(cid, str):
                text.append(cid)
            else:
                cmap = self.get_cmap(font)
                cid_char = cmap.get(cid, None)
                if cid_char:
                    text.append(cid_char)
                else:
                    text.append(f"({font}-cid:{cid})")

        unicode_text = "".join(text)
        # unicode_text = self.reorder_unicode(unicode_text)
        return unicode_text

    def merge_words_infos(self, page_words, page_infos):
        def is_mergeable(t1, t2):
            w1, w2 = t1[0], t2[0]
            # both are adjascent
            return w1.text[-1] == "्" and (w1.xmax - w2.xmin < 0.03)

        def merge_tuples(page_tuples, page_tuple):
            if not page_tuples:
                page_tuples.append(page_tuple)

            elif is_mergeable(page_tuples[-1], page_tuple):
                page_tuples[-1][0].mergeWord(page_tuple[0])
                page_tuples[-1][1].merge_info(page_tuple[1])

            else:
                page_tuples.append(page_tuple)

            return page_tuples

        page_tuples = zip(page_words, page_infos)
        merged_page_tuples = functools.reduce(merge_tuples, page_tuples, [])

        m_words, m_infos = [t[0] for t in merged_page_tuples], [t[1] for t in merged_page_tuples]
        return m_words, m_infos

    def __call__(self, doc):
        def to_doc_coords(bbox, page):
            x0, y0, x1, y1 = bbox
            coords = [
                x0 / page.width,
                (y0 / page.height),
                x1 / page.width,
                (y1 / page.height),
            ]
            return coords

        def build_word(cid_word, word_idx, page):
            text = self.get_text(cid_word, word_idx)
            doc_bbox = to_doc_coords(cid_word.bounding_box, page)
            box = Shape.build_box(doc_bbox)
            return Word(
                doc=doc,
                page_idx=page.page_idx,
                word_idx=word_idx,
                text_=text,
                break_type=BreakType.Space,
                shape_=box,
            )

        def build_word_info(cid_word):
            return WordInfo(cids=cid_word.cids, fonts=cid_word.fonts)

        doc.add_extra_page_field("word_infos", ("list", __name__, "WordInfo"))

        pdf = pdfwrapper.open(doc.pdf_path, library_name="pdfminer")
        for pdf_page, page in zip(pdf.pages, doc.pages):

            page_words = [build_word(w, idx, page) for (idx, w) in enumerate(pdf_page.cid_words)]
            page_infos = [build_word_info(w) for w in pdf_page.cid_words]

            page.words, page.word_infos = self.merge_words_infos(page_words, page_infos)

            for word, info in zip(page.words, page.word_infos):
                print(f"{page.page_idx}-{word.word_idx}: {word.text:40} {self.get_cid_str(info)}")

        return doc
