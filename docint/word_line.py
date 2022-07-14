import itertools as it
import logging
import statistics
from dataclasses import dataclass
from typing import List, Union

from .region import Region

lgr = logging.getLogger(__name__)


@dataclass
class Config:
    merge_word_len: int
    newline_height_multiple: int
    avg_height: float
    prev_ymin: float = -1.0


class LineWord(Region):
    lt_lwords: List["LineWord"] = []
    rt_lwords: List["LineWord"] = []
    position: str = "undef"
    linenum: int = -1
    char_width_: Union[int, None]
    is_merged: bool = False
    is_selected: bool = False

    @classmethod
    def build(cls, word):
        return LineWord(
            words=[word], word_idxs=[word.word_idx], page_idx_=word.page_idx
        )

    def is_short(self, config):
        return self.text_len() < config.merge_word_len

    def set_selected(self):
        self.is_selected = True

    def set_position(self):
        if not self.lt_lwords and not self.rt_lwords:
            self.position = "singleton"
        elif not self.lt_lwords:
            self.position = "first"
        elif not self.rt_lwords:
            self.position = "last"
        else:
            self.position = "middle"

    @property
    def idx_str(self):
        return "-".join([f"[{w.word_idx}]" for w in self.words])

    def to_str(self):
        words_text = " ".join(w.text for w in self.words)
        return f"[{self.words[0].word_idx}]#{len(self.words)} >{words_text}<"

    @property
    def char_width(self):
        if self.char_width_ is None:
            num_chars, wd = self.text_len(), self.shape.box.width
            self.char_width_ = 1.0 if num_chars == 0 else wd / num_chars
        return self.char_width_

    def set_side_words(self, lWords_exp, avg_height):
        def w_idx(lw):
            return lw.words[0].word_idx

        assert len(self.words) == 1
        pg = self.page
        word = self.words[0]

        lt_words = pg.words_to("left", word, overlap_percent=40, min_height=avg_height)
        rt_words = pg.words_to("right", word, overlap_percent=40, min_height=avg_height)

        # print(f'lt_words: {len(lt_words)} rt_words: {len(rt_words)}')

        self.lt_lwords = (
            [lWords_exp[w.word_idx] for w in lt_words.words] if lt_words else []
        )
        self.rt_lwords = (
            [lWords_exp[w.word_idx] for w in rt_words.words] if rt_words else []
        )

        assert all(self.lt_lwords) and all(self.rt_lwords)

        # print(f'lt_words: {len(self.lt_lwords)} rt_lwords: {len(self.rt_lwords)}')

        self.lt_lwords = [lw for lw in self.lt_lwords if id(lw) != id(self)]
        self.rt_lwords = [lw for lw in self.rt_lwords if id(lw) != id(self)]

        lt = ",".join([str(w_idx(lw)) for lw in self.lt_lwords])  # noqa: F841
        rt = ",".join([str(w_idx(lw)) for lw in self.rt_lwords])  # noqa: F841

        # print(f'[{self.words[0].word_idx}]{self.words[0].text} lt: {len(self.lt_lwords)}{lt} rt: {len(self.rt_lwords)} {rt}')

    def add_at(self, direction, lword):
        if direction == "left":
            words = lword.words + self.words

        else:
            words = self.words + lword.words
        self.words = words
        lword.is_merged = True
        # self.text_ = None
        self.shape_ = None

    def remove_side_overlap(self):
        sbox = self.shape.box
        # if self.words[0].word_idx == 130 and self.words[0].page_idx == 1:
        #    print('Found It')

        lt_ov_words = [lw for lw in self.lt_lwords if sbox.overlaps(lw.shape.box, 0.5)]
        rt_ov_words = [lw for lw in self.rt_lwords if sbox.overlaps(lw.shape.box, 0.5)]

        # print(f'Remove {self.words[0].text} lt: {len(lt_ov_words)} rt: {len(rt_ov_words)}')

        scw = self.char_width
        if lt_ov_words:
            lt_ov_long_words = [lw for lw in lt_ov_words if lw.char_width > scw]
            [lw.reduce_width_at("right", self.shape) for lw in lt_ov_long_words]

            # l_strs = [f'Reducing {lw.to_str()} at right' for lw in lt_ov_long_words]
            # print('\n'.join(l_strs))
        elif rt_ov_words:
            rt_ov_long_words = [lw for lw in rt_ov_words if lw.char_width > scw]
            [lw.reduce_width_at("left", self.shape) for lw in rt_ov_long_words]
            # r_strs = [f'Reducing {lw.to_str()} at left' for lw in rt_ov_long_words]
            # print('\n'.join(r_strs))

    def merge_side_words(self, conf):
        if self.text_len() > conf.merge_word_len:
            return

        if self.text_len() == 0:
            # print('Empty String')
            return

        # self is short word and needs to be merged
        close_lt_lwords = self.lt_lwords
        # [ lw for lw in self.lt_lwords if lw.xmax < self.xmin - 0.05  ]
        close_rt_lwords = self.rt_lwords
        # [ lw for lw in self.rt_lwords if lw.xmin > self.xmax + 0.05  ]

        if close_lt_lwords:
            rt_most_lword = max(close_lt_lwords, key=lambda lw: lw.xmax)
            gap = self.xmin - rt_most_lword.xmax
            if not rt_most_lword.is_merged and rt_most_lword.is_selected and gap < 0.05:
                # print(f'Merging {len(rt_most_lword.words)} [{rt_most_lword.words[0].word_idx}]{rt_most_lword.words[0].text} -> {self.words[0].text} [{self.words[0].word_idx}] {gap}')
                rt_most_lword.add_at("right", self)
                return True

        if close_rt_lwords:
            lt_most_lword = min(close_rt_lwords, key=lambda lw: lw.xmin)
            gap = lt_most_lword.xmin - self.xmax
            if not lt_most_lword.is_merged and lt_most_lword.is_selected and gap < 0.05:
                # print(f'MergingL {len(lt_most_lword.words)} [{lt_most_lword.words[0].word_idx}]{lt_most_lword.words[0].text} -> {self.words[0].text} [{self.words[0].word_idx}] {gap}')
                lt_most_lword.add_at("left", self)
                return True
        return False

    def set_linenum(self, slots, conf):
        nslots = len(slots)
        y_change = self.ymin - conf.prev_ymin
        y_max = conf.avg_height * conf.newline_height_multiple

        words_text = " ".join(w.text for w in self.words)

        blanked_line = " "
        if conf.prev_ymin != -1.0 and y_change > y_max:
            blank_linenum = max(slots) + 1
            slots[:nslots] = [blank_linenum] * nslots
            blanked_line = "*"  # noqa: F841

        conf.prev_ymin = self.ymin
        min_sidx, max_sidx = int(abs(self.xmin * nslots)), int(self.xmax * nslots)

        if not words_text:
            self.linenum = max(slots[min_sidx:max_sidx])
        elif min_sidx != max_sidx:
            self.linenum = max(slots[min_sidx:max_sidx]) + 1
        else:
            self.linenum = slots[min_sidx] + 1

        min_sidx = 0 if self.position in ("first", "singleton") else min_sidx
        max_sidx = nslots if self.position in ("last", "singleton") else max_sidx

        # print(f'[{self.words[0].word_idx}]#{len(self.words)}  chg:{y_change:3f} {y_max:3f}{blanked_line}[{self.xmin}:{self.xmax}]=>[{min_sidx}:{max_sidx}] LN: {self.linenum} {conf.newline_height_multiple} >{words_text}<')

        slots[min_sidx:max_sidx] = [self.linenum] * (max_sidx - min_sidx)
        return self.linenum


def print_word_lines(word_lines):
    for (line_idx, line) in enumerate(word_lines):
        line = " ".join([w.text for w in line])
        print(f"[{line_idx}]: {line}")


def words_in_lines(
    region,
    *,
    merge_word_len=3,
    num_slots=1000,
    newline_height_multiple=1.0,
    para_indent=True,
    is_page=False,
):
    if not region or not region.words:
        return []

    first_word = region.words[0]
    avg_height = statistics.mean([w.box.height for w in region.words])
    conf = Config(merge_word_len, newline_height_multiple, avg_height)

    page_words = first_word.page.words if not is_page else region.words

    page_lWords = [LineWord.build(word) for word in page_words]
    lWords = [page_lWords[w.word_idx] for w in region.words]

    [lw.set_selected() for lw in lWords]

    [lw.set_side_words(page_lWords, avg_height) for lw in lWords]
    [lw.set_position() for lw in lWords]

    lWords.sort(key=lambda lw: lw.ymin)

    slots = [0] * num_slots
    if para_indent:
        first_word = next(lw for lw in lWords if lw.position == "first")
        first_slot_idx = int(first_word.xmin * num_slots) - 5  # TODO
        first_slot_idx = max(first_slot_idx, 0)
        slots[:first_slot_idx] = [1] * first_slot_idx
    # end

    # Using side words remove side overlap
    [lw.remove_side_overlap() for lw in lWords]

    # print(f'# Before lWords: {len(lWords)} {[lW.idx_str for lW in lWords]}')
    # merge short words and remove merged words
    [lw.merge_side_words(conf) for lw in lWords if lw.is_short(conf)]
    lWords = [lw for lw in lWords if not lw.is_merged]
    # print(f'# After lWords: {len(lWords)} {[lW.idx_str for lW in lWords]}')

    # set the positions again as merging could have changed the words
    [lw.set_position() for lw in lWords]

    # set the line number and sort the line words
    [lw.set_linenum(slots, conf) for lw in lWords]
    lWords.sort(key=lambda lw: (lw.linenum, lw.xmin))

    max_lines = max([lw.linenum for lw in lWords]) + 1
    word_lines = [[] for _ in range(max_lines)]

    for linenum, lw_group in it.groupby(lWords, key=lambda lw: lw.linenum):
        word_lines[linenum].extend([w for lw in lw_group for w in lw.words])

    num_words = sum([len(wl) for wl in word_lines])
    assert len(region.words) == num_words

    # print_word_lines(word_lines)
    return word_lines


# Simple words_in_lines, this big one should be moved to Page as it tries to find
# left and right words which make sense only in a page, where all words need to be
# processed. For smaller words they shoudl go to page and their ordering.
#
# Till we implement that logic as that is going to be disruptive, implementing a
# hopefully smaller and simpler method.


def words_in_lines_short(words, num_slots=1000):
    # moved to region.py to avoid circular dependency
    pass
