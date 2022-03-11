from pydantic import BaseModel
from typing import List, Union
import logging


from dataclasses import dataclass
import itertools as it
import statistics

from .region import Region

lgr = logging.getLogger(__name__)


@dataclass
class Config:
    merge_word_len: int
    newline_height_multiple: int
    avg_height: float
    prev_ymin: float = -1.0


class LineWord(Region):
    lt_lwords: List['LineWord'] = []
    rt_lwords: List['LineWord'] = []
    position: str = "undef"
    linenum: int = -1
    char_width_: Union[int, None]
    is_merged: bool = False
    is_selected: bool = False

    @classmethod
    def build(cls, word):
        return LineWord(words=[word])

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
        return '-'.join([f'[{w.word_idx}]' for w in self.words])

    @property
    def char_width(self):
        if self.char_width_ is None:
            num_chars, wd = self.text_len(), self.shape.box.width
            self.char_width_ = 1.0 if num_chars == 0 else wd / num_chars
        return self.char_width_

    def set_side_words(self, lWords_exp, avg_height):
        assert len(self.words) == 1
        pg = self.page
        word = self.words[0]
            
        lt_words = pg.words_to("left", word, overlap_percent=40, min_height=avg_height)
        rt_words = pg.words_to("right", word, overlap_percent=40, min_height=avg_height)

        #print(f'lt_words: {len(lt_words)} rt_words: {len(rt_words)}')

        self.lt_lwords = (
            [lWords_exp[w.word_idx] for w in lt_words.words] if lt_words else []
        )
        self.rt_lwords = (
            [lWords_exp[w.word_idx] for w in rt_words.words] if rt_words else []
        )

        assert all(self.lt_lwords) and all(self.rt_lwords)

        #print(f'lt_words: {len(self.lt_lwords)} rt_lwords: {len(self.rt_lwords)}')        

        self.lt_lwords = [lw for lw in self.lt_lwords if id(lw) != id(self)]
        self.rt_lwords = [lw for lw in self.rt_lwords if id(lw) != id(self)]

        lt_str = ','.join([str(lw.words[0].word_idx) for lw in self.lt_lwords])
        rt_str = ','.join([str(lw.words[0].word_idx) for lw in self.rt_lwords])        

        #print(f'[{self.words[0].word_idx}]{self.words[0].text} lt: {len(self.lt_lwords)}{lt_str} rt: {len(self.rt_lwords)} {rt_str}')
        

    def add_at(self, direction, lword):
        if direction == "left":
            words = lword.words + self.words

        else:
            words = self.words + lword.words
        self.words = words
        lword.is_merged = True
        self.text_ = None
        self.shape_ = None
            

    def remove_side_overlap(self):
        sbox = self.shape.box
        lt_ov_words = [lw for lw in self.lt_lwords if sbox.overlaps(lw.shape.box)]
        rt_ov_words = [lw for lw in self.rt_lwords if sbox.overlaps(lw.shape.box)]

        #print(f'{self.words[0].text} lt: {len(lt_ov_words)} rt: {len(rt_ov_words)}')        

        scw = self.char_width
        if lt_ov_words:
            lt_ov_long_words = [lw for lw in lt_ov_words if lw.char_width > scw]
            [lw.reduce_width_at("right", self.shape) for lw in lt_ov_long_words]
        else:
            rt_ov_long_words = [lw for lw in rt_ov_words if lw.char_width > scw]
            [lw.reduce_width_at("left", self.shape) for lw in rt_ov_long_words]

    def merge_side_words(self, conf):
        if self.text_len() > conf.merge_word_len:
            return
                    
        if self.text_len() == 0:
            print('Empty String')
            return 

        # self is short word and needs to be merged
        
        if self.lt_lwords:
            rt_most_lword = max(self.lt_lwords, key=lambda lw: lw.xmax)
            if not rt_most_lword.is_merged and rt_most_lword.is_selected:
                #print(f'Merging {len(rt_most_lword.words)} [{rt_most_lword.words[0].word_idx}]{rt_most_lword.words[0].text} -> {self.words[0].text} [{self.words[0].word_idx}]')
                rt_most_lword.add_at("right", self)
                return True

        if self.rt_lwords:
            lt_most_lword = min(self.rt_lwords, key=lambda lw: lw.xmin)
            if not lt_most_lword.is_merged and lt_most_lword.is_selected:
                #print(f'MergingL {len(lt_most_lword.words)} [{lt_most_lword.words[0].word_idx}]{lt_most_lword.words[0].text} -> {self.words[0].text} [{self.words[0].word_idx}]')
                lt_most_lword.add_at("left", self)
                return True
        return False

    def set_linenum(self, slots, conf):
        nslots = len(slots)

        y_change = self.ymin - conf.prev_ymin
        y_max = conf.avg_height * conf.newline_height_multiple

        words_text = ' '.join(w.text for w in self.words)
        #print(f'[{self.words[0].word_idx}]#{len(self.words)}  chg:{y_change:3f} {y_max:3f} {conf.newline_height_multiple} {words_text}')
        if conf.prev_ymin != -1.0 and y_change > y_max:
            blank_linenum = max(slots) + 1
            slots[:nslots] = [blank_linenum] * nslots

        conf.prev_ymin = self.ymin
        min_sidx, max_sidx = int(abs(self.xmin * nslots)), int(self.xmax * nslots)

        if min_sidx != max_sidx:
            self.linenum = max(slots[min_sidx:max_sidx]) + 1
        else:
            self.linenum = slots[min_sidx] + 1

        min_sidx = 0 if self.position in ("first", "singleton") else min_sidx
        max_sidx = nslots if self.position in ("last", "singleton") else max_sidx

        slots[min_sidx:max_sidx] = [self.linenum] * (max_sidx - min_sidx)
        return self.linenum

def print_word_lines(word_lines):
    for (line_idx, line) in enumerate(word_lines):
        line = ' '.join([w.text for w in line])
        print(f'[{line_idx}]: {line}')


def words_in_lines(
    region,
    *,
    merge_word_len=3,
    num_slots=1000,
    newline_height_multiple=1.0,
    para_indent=True
):
    if not region or not region.words:
        return []

    first_word = region.words[0]
    avg_height = statistics.mean([w.box.height for w in region.words])
    conf = Config(merge_word_len, newline_height_multiple, avg_height)

    page_lWords = [LineWord.build(word) for word in first_word.page.words ]
    lWords = [page_lWords[w.word_idx] for w in region.words ]

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

    #print(f'# Before lWords: {len(lWords)} {[lW.idx_str for lW in lWords]}')    
    # merge short words and remove merged words
    [lw.merge_side_words(conf) for lw in lWords if lw.is_short(conf)]
    lWords = [lw for lw in lWords if not lw.is_merged]
    #print(f'# After lWords: {len(lWords)} {[lW.idx_str for lW in lWords]}')    

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

    #print_word_lines(word_lines)
    return word_lines
