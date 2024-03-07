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
    for idx, val in zip(range(start_idx - 1, -1, -1), lst[start_idx - 1 :: -1]):
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
        "fix_number_strs": True,
        "edit_cid_words": {},
        "edit_words": {},
        "swap_cids": [],
    },
)
class PDFCIDReader:
    def __init__(
        self, cmaps_dir, stub, output_dir, fix_number_strs, edit_cid_words, edit_words, swap_cids
    ):
        self.cmaps_dir = Path(cmaps_dir)
        self.output_dir_path = Path(output_dir)
        self.stub = stub
        self.conf_dir = Path("conf")
        self.fix_number_strs = fix_number_strs
        self.edit_cid_words = {}
        self.edit_words = {}
        self.swap_cids = swap_cids
        self.missing_cmaps = set()

        self.font_cmap_dict = {}

    def get_cmap(self, font):
        if font in self.font_cmap_dict:
            return self.font_cmap_dict[font]

        yaml_file = self.cmaps_dir / f"{font}.yml"
        if yaml_file.exists():
            self.font_cmap_dict[font] = yaml.load(yaml_file.read_text(), Loader=yaml.FullLoader)
        else:
            self.font_cmap_dict[font] = {}

        return self.font_cmap_dict[font]

    def get_cid_str(self, info):
        cid_str_dict = {}
        for font, cid in zip(info.fonts, info.cids):
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
            # 2325:क, 2361:ह, 2309:अ 2314:ऊ,
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
            if not cmap:
                self.missing_cmaps.add(font)
                #print(f"cmap NotFound {font} {cid}")
                return None

            cid_char = cmap.get(cid, None)
            # assert cid_char, f'{font} {cid}'
            if cid_char is None:
                print(f"NotFound {font} {cid}")
            return cid_char

    def reorder_cids(self, w_cids, w_fonts):
        def get_cmds(cmd):
            cmds = []
            for idx, (cid, font) in enumerate(zip(result, fonts)):
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
        for repl_idx, repl_cmd in replace_cmds:
            repl_idx += num_cids_added
            result.pop(repl_idx)
            repl_font = fonts.pop(repl_idx)

            for new_cid in reversed(repl_cmd[1:]):
                result.insert(repl_idx, new_cid)
                fonts.insert(repl_idx, repl_font)
            num_cids_added += len(repl_cmd[1:]) - 1  # since first value is replaced

        move_left_cmds = get_cmds("move_left")
        for ml_idx, ml_cmd in move_left_cmds:
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

            # assert ins_idxs, f'{result} {move_left_cmds}'

            ins_idx = ins_idxs[0]

            # switching not chaning the font !
            ml_cid = result.pop(ml_idx)  # noqa
            result.insert(ins_idx, ml_cmd[-1])

        move_right_cmds = get_cmds("move_right")
        for mr_idx, mr_cmd in reversed(move_right_cmds):
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
        reordered_cids, reordered_fonts = self.reorder_cids(cid_word.cids, cid_word.fonts)

        for font, cid in zip(reordered_fonts, reordered_cids):
            if isinstance(cid, str):
                text.append(cid)
            else:
                cmap = self.get_cmap(font)
                if not cmap:
                    text.append(f"({font}-cid:{cid})")
                    continue

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
        "Merge words that are closeby and are x overlapping, bounding box is increased."

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

    def edit_word_cids(self, cid_words, page_idx, cfg):
        """This methods makes edits as per config file, each is document specific
        1. space_cid_fonts: Remove all words with this font, useful for removing gibberish.
                            # [ 'sakalmarathi' ]
        2. space_words: Replace these words with space, useful for removing words
                        # space_words: [ 'pa37.wo81' ]
        3. edit_cid_words: change text based on *(font and cids)*.
                           # {'mangal': [{'cids': [1,2,3], 'text': 'उद्भवत'}], 'sakalbharti'...}
        4. edit_words: change text based on *word_idx*
                       # {'pa17.wo224': 'उद्भवल्याचे', 'pa17.wo224': 'श्री जयंत'}

        5. swap_cids: swap the cids of these consecutive two words
                       # [['sakalmarathi', 161, 245]]

        """
        if not cfg:
            return cid_words

        space_fonts = set(cfg.get("space_cid_fonts", []))
        space_words = set(cfg.get("space_words", []))

        edit_cids = cfg.get("edit_cid_words", {})
        edit_words = cfg.get("edit_words", {})

        assert all(sf not in edit_cids for sf in space_fonts), "space_fonts & edit_cids shld be xcl"
        for word_idx, cid_word in enumerate(cid_words):
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

            if cfg["swap_cids"] and cid_word.cids:
                cids, fonts, swap_idxs = cid_word._cids, cid_word._fonts, []
                for font, cid1, cid2 in cfg["swap_cids"]:
                    for idx in range(len(cid_word.cids) - 1):
                        if (
                            (fonts[idx] == font)
                            and (fonts[idx + 1] == font)
                            and (cids[idx] == cid1)
                            and cids[idx + 1] == cid2
                        ):
                            swap_idxs.append(idx)
                if swap_idxs:
                    for idx in swap_idxs:
                        cid_word._cids[idx], cid_word._cids[idx + 1] = (
                            cid_word._cids[idx + 1],
                            cid_word._cids[idx],
                        )

        return cid_words

    def fix_word_str(self, cid_word):
        def to_fix(cid_char):
            return isinstance(cid_char, str) and cid_char.isdigit() and cid_char.isascii()

        deva = "०१२३४५६७८९"
        cid_word._cids = [deva[int(c)] if to_fix(c) else c for c in cid_word.cids]
        return cid_word

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
            return WordInfo(
                cids=cid_word.cids, fonts=cid_word.fonts, line_widths=cid_word.line_widths
            )

        # print(f"> pdf_cid_reader: {doc.pdf_name}")

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

        cfg["edit_cid_words"] = cfg.get("edit_cid_words", self.edit_cid_words)
        cfg["edit_words"] = cfg.get("edit_words", self.edit_words)
        cfg["swap_cids"] = cfg.get("swap_cids", self.swap_cids)

        pdf = pdfwrapper.open(doc.pdf_path, library_name="pdfminer")

        for pdf_page, page in zip(pdf.pages, doc.pages):
            page_cid_words = self.merge_word_cids(pdf_page.cid_words, page.page_idx)
            page_cid_words = self.edit_word_cids(page_cid_words, page.page_idx, cfg)

            if self.fix_number_strs:
                page_cid_words = [self.fix_word_str(w) for w in page_cid_words]

            # page_cid_word_strs = [f"{c.cids}" for c in page_cid_words]

            page.words = [build_word(w, idx, page) for (idx, w) in enumerate(page_cid_words)]
            page.word_infos = [build_word_info(w) for w in page_cid_words]

            # print(
            #     "\n".join(
            #         [
            #             f"{page.page_idx}[{w.word_idx}]: {w.text}-{s}"
            #             for idx, (w, s) in enumerate(zip(page.words, page_cid_word_strs))
            #         ]
            #     )
            # )

        # doc.to_disk(doc_gz_path)

        # print(f"< pdf_cid_reader: {doc.pdf_name}")
        if self.missing_cmaps:
            print(f'\t{doc.pdf_name} missing_cmaps: {", ".join(self.missing_cmaps)}')
        return doc
