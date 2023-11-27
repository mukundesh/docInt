import copy
import functools
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
    for (idx, val) in zip(range(start_idx - 1, -1, -1), lst[start_idx - 1 :: -1]):
        yield idx, val


class WordInfo(BaseModel):
    cids: List[Any]
    fonts: List[str]
    line_widths: List[float]

    def merge_info(self, info):
        self.cids.extend(info.cids)
        self.fonts.extend(info.fonts)


@Vision.factory(
    "pdf_cid_reader",
    default_config={
        "cmaps_dir": "conf/cmaps",
        "stub": "pdf_cid_reader",
        "output_dir": "output",
    },
)
class PDFCIDReader:
    def __init__(self, cmaps_dir, stub, output_dir):
        self.cmaps_dir = Path(cmaps_dir)
        self.output_dir_path = Path(output_dir)
        self.stub = stub
        self.conf_dir = Path("conf")

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

    def is_unichr_cid(self, cid, font):
        if isinstance(cid, str):
            return False

        cmap = self.get_cmap(font)
        uc = cmap[cid]

        if not uc:
            return False
        if len(uc) == 1:
            return (2325 <= ord(uc) <= 2361) or (2309 <= ord(uc) <= 2314)
        elif len(uc) >= 3:
            return True
        else:
            return False

        # return False if not uc or len(uc) > 1 else 2325 <= ord(uc) <= 2361

    def get_cid_char(self, cid, font):
        if isinstance(cid, str):
            return cid
        else:
            cmap = self.get_cmap(font)
            cid_char = cmap.get(cid, None)
            # assert cid_char, f'{font} {cid}'
            if cid_char is None:
                print(f"NotFound {font} {cid}")
            return cid_char

    def reorder_cids2(self, w_cids, w_fonts):
        def get_cmds(cmd):
            cmds = []
            for (idx, (cid, font)) in enumerate(zip(result, fonts)):
                cid_char = self.get_cid_char(cid, font)
                if isinstance(cid_char, list) and cid_char[0] == cmd:
                    cmds.append((idx, cid_char))
            return cmds

        def is_vovel_i(idx):
            cid_char = self.get_cid_char(result[idx], fonts[idx])
            return cid_char == "इ"

        # if cfg has cids that need to be swapped
        result, fonts = w_cids, w_fonts

        # replace_cmd = [ 'replace', 91, 546, 562 ] # this is for Mangal

        replace_cmds = get_cmds("replace")
        num_cids_added = 0
        for (repl_idx, repl_cmd) in replace_cmds:
            repl_idx += num_cids_added
            result.pop(repl_idx)
            repl_font = fonts.pop(repl_idx)

            for new_cid in reversed(repl_cmd[1:]):
                result.insert(repl_idx, new_cid)
                fonts.insert(repl_idx, repl_font)
            num_cids_added += len(repl_cmd[1:]) - 1  # since first value is replaced

        move_left_cmds = get_cmds("move_left")
        for (ml_idx, ml_cmd) in move_left_cmds:
            if ml_cmd[-1] == "र्" and is_vovel_i(ml_idx - 1):  # is इ
                print("REMOVING Reph as it is mistaken for इ")
                result.pop(ml_idx)
                fonts.pop(ml_idx)
                continue

            ins_idxs = [
                idx
                for (idx, cid) in rev_enumerate(result, ml_idx)
                if self.is_unichr_cid(cid, fonts[idx])
            ]

            if not ins_idxs:
                continue

                import pdb

                pdb.set_trace()

            # assert ins_idxs, f'{result} {move_left_cmds}'

            ins_idx = ins_idxs[0]

            # switching not chaning the font !
            ml_cid = result.pop(ml_idx)  # noqa
            result.insert(ins_idx, ml_cmd[-1])

        move_right_cmds = get_cmds("move_right")
        for (mr_idx, mr_cmd) in move_right_cmds:
            ins_idxs = [
                idx
                for (idx, cid) in enumerate(result[mr_idx:], mr_idx)
                if self.is_unichr_cid(cid, fonts[idx])
            ]

            ins_idx = ins_idxs[0] if ins_idxs else len(result)
            mr_cid = result.pop(mr_idx)  # noqa
            result.insert(ins_idx, mr_cmd[-1])

        return result, fonts

    def get_text(self, cid_word, word_idx):
        text = []
        # : क्र -> क ् र
        # : निर्ण -> न ि र ् ण
        # : पर्या -> प र ् य ा
        # : कार्य -> क ा र ् य

        # keep the original orders
        reordered_cids, reordered_fonts = self.reorder_cids2(cid_word.cids, cid_word.fonts)

        for (font, cid) in zip(reordered_fonts, reordered_cids):
            if isinstance(cid, str):
                text.append(cid)
            else:
                cmap = self.get_cmap(font)
                cid_char = cmap.get(cid, None)
                if cid_char:
                    # TODO this should be removed
                    if isinstance(cid_char, list):
                        continue

                    text.append(cid_char)
                else:
                    text.append(f"({font}-cid:{cid})")

        unicode_text = "".join(text)
        # print(f'{word_idx}: {unicode_text}')
        return unicode_text

    def merge_word_cids(self, cid_words, page_idx):
        def is_mergeable(w1, w2):
            # cid_char = self.get_cid_char(w1.cids[-1], w1.fonts[-1])

            # if cid_char is None:
            #     print(f'Missing {w1.cids[-1]} {w1.fonts[-1]}')
            #     return False
            # assert cid_char is not None,
            # print(f'cid_char: {cid_char} w2_xmin: {w2_xmin:.2f} w1_xmax: {w1_xmax:.2f} diff: {w2_xmin - w1_xmax}')
            # return "्" in cid_char  and (w2_xmin - w1_xmax < 3)

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

    def edit_word_cids(self, cid_words, page_idx, cfg):
        if not cfg:
            return cid_words

        space_fonts = set(cfg.get("space_cid_fonts", []))
        space_words = set(cfg.get("space_words", []))

        edit_cids = cfg.get("edit_cid_words", {})
        edit_words = cfg.get("edit_words", {})

        assert all(sf not in edit_cids for sf in space_fonts), "space_fonts & edit_cids shld be xcl"
        for word_idx, cid_word in enumerate(cid_words):

            # if page_idx == 1 and word_idx == 171:
            #     import pdb
            #     pdb.set_trace()
            #     pass

            fonts = set(cid_word.fonts)
            word_path = f"pa{page_idx}.wo{word_idx}"
            if word_path in space_words:
                print(f"spacing_word: {word_path}: {fonts} {cid_word.cids}")
                cid_word._cids = [" "] * len(cid_word.cids)
            elif word_path in edit_words:
                cid_word._cids = list(edit_words[word_path])
                print(f"editing_word: {word_path}: {edit_words[word_path]}")

            if len(fonts) > 1:
                continue

            font = fonts.pop()
            if font in space_fonts:
                print(f"spacing_font: {word_path}: {font}: {cid_word.cids}")
                cid_word._cids = [" "] * len(cid_word.cids)
            elif font in edit_cids:
                cid_infos = edit_cids.get(font)
                cid_info = first((ci for ci in cid_infos if ci["cids"] == cid_word.cids), None)
                if cid_info:
                    cid_word._cids = list(cid_info["text"])
                    print(f'editing_cid_words: {word_path}: {font}: {cid_info["text"]}')
        return cid_words

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
            # if word_idx == 203 and page.page_idx == 4 :
            #      import pdb
            #      pdb.set_trace()

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
            return WordInfo(
                cids=cid_word.cids, fonts=cid_word.fonts, line_widths=cid_word.line_widths
            )

        print(f"> pdf_cid_reader: {doc.pdf_name}")

        doc_path = self.output_dir_path / f"{doc.pdf_name}.ocr.json"
        doc_gz_path = self.output_dir_path / f"{doc.pdf_name}.ocr.json.gz"
        if doc_path.exists():
            print("Reading doc.json")
            doc = Doc.from_disk(doc_path)
            doc.pipe_names[:-1] = []
            return doc

        if doc_gz_path.exists():
            print("Reading doc.json")
            doc = Doc.from_disk(doc_gz_path)
            doc.pipe_names[:-1] = []
            return doc

        doc.add_extra_page_field("word_infos", ("list", __name__, "WordInfo"))
        cfg = load_config(self.conf_dir, doc.pdf_name, self.stub)

        pdf = pdfwrapper.open(doc.pdf_path, library_name="pdfminer")
        missing_found = False
        for pdf_page, page in zip(pdf.pages, doc.pages):

            page_cid_words = self.merge_word_cids(pdf_page.cid_words, page.page_idx)
            page_cid_words = self.edit_word_cids(page_cid_words, page.page_idx, cfg)

            page.words = [build_word(w, idx, page) for (idx, w) in enumerate(page_cid_words)]
            page.word_infos = [build_word_info(w) for w in page_cid_words]

            # page.words, page.word_infos = self.merge_words_infos(page_words, page_infos)

            for word, info in zip(page.words, page.word_infos):
                if "cid:" in word.text:
                    missing_found = True
                    has_width = any(lw != 0 for lw in info.line_widths)
                    print(
                        f"{doc.pdf_name} {page.page_idx}-{word.word_idx}: {word.text:40} {self.get_cid_str(info)} has_width: {has_width}"
                    )

        if missing_found:
            print(f"Missing Found {doc.pdf_name}, quitting")
            raise ValueError(f"Missing found in {doc.pdf_name}")

        doc.to_disk(doc_gz_path)

        print(f"< pdf_cid_reader: {doc.pdf_name}")
        return doc

    # def reorder_cids(self, w_cids, w_fonts):
    #     double_cids = {
    #         568: (91, 546),
    #         569: (91, 546),
    #         570: (91, 546),
    #         571: (91, 546),
    #         572: (91, 546),
    #         573: (91, 546),
    #         574: (91, 554),
    #         575: (91, 555),
    #         576: (91, 558),
    #         577: (91, 553),
    #         588: (91, 561),
    #         589: (91, 562),

    #         600: (91, 546, 562),
    #         601: (91, 546, 562),
    #         602: (91, 546, 562),
    #         603: (91, 546, 562),
    #         604: (91, 546, 562),
    #         605: (91, 546, 562),

    #     }

    #     #result, fonts = w_cids[:], w_fonts[:]
    #     result, fonts = w_cids, w_fonts

    #     num_cids_added = 0

    #     double_idxs = [idx for (idx, cid) in enumerate(result) if cid in double_cids]
    #     for (idx, double_idx) in enumerate(double_idxs):

    #         double_idx += num_cids_added  # as we are adding an extra character
    #         double_cid = result.pop(double_idx)

    #         assert double_cid in double_cids
    #         double_font = fonts.pop(double_idx)

    #         new_cids = double_cids[double_cid]

    #         for new_cid in reversed(new_cids):
    #             result.insert(double_idx, new_cid)
    #             fonts.insert(double_idx, double_font)
    #         num_cids_added += len(new_cids) - 1

    #     rph_idxs = [idx for (idx, cid) in enumerate(result) if cid == 91]
    #     for rph_idx in rph_idxs:
    #         u_idxs = [
    #             idx
    #             for (idx, cid) in rev_enumerate(result, rph_idx)
    #             if self.is_unichr_cid(cid, fonts[idx])
    #         ]
    #         u_idx = u_idxs[0]
    #         rph = result.pop(rph_idx)
    #         result.insert(u_idx, rph)

    #     matra_cids = [464, 465, 466, 467, 468, 871, 872, 873, 874, 875, 876, 877, 878, 879]
    #     matra_idxs = [idx for (idx, cid) in enumerate(result) if cid in matra_cids]

    #     for matra_idx in matra_idxs:
    #         u_idxs = [
    #             idx
    #             for (idx, cid) in enumerate(result[matra_idx:], matra_idx)
    #             if self.is_unichr_cid(cid, fonts[idx])
    #         ]
    #         u_idx = u_idxs[0] if u_idxs else len(result)
    #         matra = result.pop(matra_idx)
    #         result.insert(u_idx, matra)

    #     return result, fonts

    # def merge_words_infos(self, page_words, page_infos):
    #     def is_mergeable(t1, t2):
    #         w1, w2 = t1[0], t2[0]
    #         # both are adjascent
    #         return w1.text[-1] == "्" and (w1.xmax - w2.xmin < 0.03)

    #     def merge_tuples(page_tuples, page_tuple):
    #         if not page_tuples:
    #             page_tuples.append(page_tuple)

    #         elif is_mergeable(page_tuples[-1], page_tuple):
    #             page_tuples[-1][0].mergeWord(page_tuple[0])
    #             page_tuples[-1][1].merge_info(page_tuple[1])

    #         else:
    #             page_tuples.append(page_tuple)

    #         return page_tuples

    #     page_tuples = zip(page_words, page_infos)
    #     merged_page_tuples = functools.reduce(merge_tuples, page_tuples, [])

    #     m_words, m_infos = [t[0] for t in merged_page_tuples], [t[1] for t in merged_page_tuples]
    #     return m_words, m_infos
