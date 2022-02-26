from typing import List, Dict
from itertools import zip_longest, groupby

from pydantic import BaseModel

from rich.text import Text
from rich import print as rprint


from .word import Word
from .shape import Shape, Box, Coord


class TextConfig(BaseModel):
    rm_labels: List[str] = []
    rm_nl: bool = True


class Span(BaseModel):
    start: int
    end: int
    label: str

    def __len__(self):
        return self.end - self.start

    def __contains__(self, pos):
        #print(f'\t\t{pos} in {self.start}:{self.end}', end=" result> ")
        if isinstance(pos, int):
            res = self.start <= pos < self.end
        else:
            s, e = pos
            res = self.overlap(s, e) > 0
        #print(res)
        return res

    def overlap(self, s, e):
        min_end, max_start = min(e, self.end), max(s, self.start)
        return max(0,  min_end - max_start)


    def update(self, pos, inc):
        if self.start >= pos:
            self.start += inc
            self.end += inc
        elif self.start < pos < self.end:
            self.end += inc

        self.start = max(self.start, 0)
        self.end = max(self.end, 0)

class Region(BaseModel):
    words: List[Word]
    text_: str = None
    shape_: Box = None
    word_lines: List[List[Word]] = None
    label_spans: Dict[str, List[Span]] = {}


    def __len__(self):
        return len(self.words)

    def __bool__(self):
        # What is an empty region, what if remove the words from a
        # a region after words
        return bool(self.words)

    @property
    def doc(self):
        return self.words[0].doc

    @property
    def page_idx(self):
        return self.words[0].page_idx

    @property
    def page(self):
        return self.doc.pages[self.page_idx]

    def str_spans(self):
        t = self.line_text()
        label_strs = []
        for label, spans in self.label_spans.items():
            spanStrs = [f'[{s.start}:{s.end}]=>{t[s.start:s.end]}<' for s in spans]
            label_strs.append(f'{label}: {" ".join(spanStrs)}')
        return '\n'.join(label_strs)

    def text_len(self):
        # should we eliminate zero words ? not now
        text_lens = [len(w.text) for w in self.words]
        num_spaces = len(text_lens) - 1
        return sum(text_lens) + num_spaces if text_lens else 0

    def text_isalnum(self):
        # should we eliminate zero words ? not now
        return all([w.text.isalnum() for w in self.words])

    def iter_words(self):
        for word_line in self.word_lines:
            new_line = [w for w in word_line if w]
            for idx, word in enumerate(new_line):
                yield idx, word

    # def iter_word_pairs(self):
    #     for word_line in self.word_lines:
    #         line = [w for w in word_line if w]
    #         for (word, next_word) in zip_longest(line, line[1:], fillvalue=None):
    #             yield word, next_word


    def iter_words_startpos(self, text_config=None):
        tc = text_config
        rm_spans = self.get_non_overlap_spans(tc.rm_labels) if tc is not None else []
        start_pos = 0
        for word_line in self.word_lines:
            new_line = [w for w in word_line if w]
            for idx, word in enumerate(new_line):
                if not any(start_pos in s for s in rm_spans):
                    yield start_pos, word
                else:
                    pass
                    #print(f'Skipping {word.text} {start_pos}')
                start_pos += len(word.text) + 1
        
        

    def iter_words(self, text_config=None):
        tc = text_config
        rm_spans = self.get_non_overlap_spans(tc.rm_labels) if tc is not None else []

        start_pos = 0
        for word_line in self.word_lines:
            new_line = [w for w in word_line if w]
            for idx, word in enumerate(new_line):
                #print(f'\tChecking {word.text} start_pos:{start_pos}')
                if not any(start_pos in s for s in rm_spans):
                    yield idx, word
                else:
                    pass
                    #print(f'Skipping {word.text} {start_pos}')
                start_pos += len(word.text) + 1


    def iter_word_text(self, text_config=None):

        ## Optmize this, rm_spans is small, but still !!
        def get_overlap_type(rm_spans, word_start, word_end):
            word_len = word_end - word_start
            for span in rm_spans:
                overlap_len = span.overlap(word_start, word_end)
                if overlap_len == word_len:
                    return 'full', span
                elif 0 < overlap_len < word_len:
                    return 'partial', span
            return 'none', None

        tc = text_config
        rm_spans = self.get_non_overlap_spans(tc.rm_labels) if tc is not None else []

        #print(f'rm_spans: {len(rm_spans)}')

        start_pos = 0
        for word_line in self.word_lines:
            new_line = [w for w in word_line if w]

            word_text_line = []
            for word in new_line:
                end_pos = start_pos + len(word.text)
                o_type, o_span  = get_overlap_type(rm_spans, start_pos, end_pos)
                #print(f'\tChecking {word.text}[{start_pos}:{end_pos}] {o_type}')
                if o_type == 'none':
                    yield word.text, word
                elif o_type == 'partial':
                    print(f'\t\tPartial: full:{word.text} {o_span.start}:{o_span.end}', end=" ")
                    assert not (start_pos < o_span.start < o_span.end < end_pos)
                    if o_span.end < end_pos:
                        non_overlap_text = word.text[o_span.end-start_pos:]
                    else:
                        non_overlap_text = word.text[:o_span.start-start_pos]
                    print(f'non_overlap:{non_overlap_text}')                        
                    yield non_overlap_text, word
                else:
                    pass
                    #print(f'\t\tfull: {word.text}')
                start_pos += len(word.text) + 1

    def get_spans(self, label):
        return self.label_spans.get(label, [])

    def get_span_text(self, span):
        text = self.line_text()
        return text[span.start:span.end]

    def get_span_words(self, span):
        span_words = []
        for start_pos, word in self.iter_words_startpos():
            end_pos = start_pos + len(word.text)
            if (start_pos, end_pos) in span:
                span_words.append(word)
        return span_words


    def iter_word_pairs(self, text_config=None):
        if text_config is not None:
            rm_spans = self.get_non_overlap_spans(text_config.rm_labels)
        else:
            rm_spans = []

        def in_spans(pos):
            return any(pos in s for s in rm_spans)

        start_pos = 0
        for word_line in self.word_lines:
            line = [w for w in word_line if w]
            for (word, next_word) in zip_longest(line, line[1:], fillvalue=None):
                next_start_pos = start_pos + len(word)
                next_start_pos += 1 if next_word != None else 0 # add space
                if not in_spans(start_pos) and not in_spans(next_start_pos):
                    yield word, next_word
                else:
                    pass
                    #print(f'\tSkipping {word.text} {start_pos} {next_start_pos}')
                start_pos += len(word.text) + 1 # add space

    def get_text_idx_atstart(self, find_word):
        idx = 0
        #print(f"find_idx: {find_word.word_idx}")
        for line_idx, word in self.iter_words():
            #print(f'{find_word.word_idx} == {word.word_idx}')
            if find_word.word_idx == word.word_idx:
                return idx
            idx += len(word.text) + 1
        assert False

    def get_non_overlap_spans(self, labels):
        spans = [s for label in labels for s in self.label_spans.get(label, [])]

        new_spans = []
        #print(f"len_spans: {len(spans)}")
        if spans:
            max_idx = max([s.end for s in spans])
            span_marker = [False] * max_idx
            for span in spans:
                #print(f"setting [{span.start}:{span.end}] {len(spans)}")
                span_marker[span.start:span.end] = [True] * len(span)

            for key, group in groupby(enumerate(span_marker), key=lambda tup: tup[1]):
                if key:
                    group = list(group)
                    start, end = group[0][0], group[-1][0] + 1
                    #print(f"group start: {start}, end: {end}")
                    new_span = Span(start=start, end=end, label="NOLABEL")
                    new_spans.append(new_span)

        #print(f"\trm len(non_overlapping_spans): {len(new_spans)}")
        return new_spans

    def line_text(self, text_config=None):
        word_texts = [w.text for wl in self.word_lines for w in wl if w]
        line_text = " ".join(word_texts)

        if text_config is None:
            return line_text

        if text_config.rm_nl:
            line_text.replace("\n", " ")

        #print(f"Line: {line_text}")

        line_text = list(line_text)
        for rm_span in self.get_non_overlap_spans(text_config.rm_labels):
            #print(f"start: {rm_span.start} end: {rm_span.end} label: {rm_span.label}")
            line_text[rm_span.start:rm_span.end] = "|" * len(rm_span)

        line_text = "".join(line_text)
        return line_text.replace("|", "")

    def print_color(self, error_type, color_config):
        line_text = self.line_text()
        color_text = Text(error_type + line_text)
        elen = len(error_type)
        for label, spans in self.label_spans.items():
            color = color_config.get(label, None)
            if color:
                [ color_text.stylize(color, s.start + elen, s.end + elen) for s in spans ]
        #end for
        rprint(color_text)
        

    def update_all_spans(self, text_idx, inc):
        [s.update(text_idx, inc) for spans in self.label_spans.values() for s in spans]

    def merge_word(self, keep_word, elim_word):
        #assert self.is_consecutive(keep_word, elim_word)
        assert len(keep_word) != 0 and len(elim_word) != 0

        elim_idx = self.get_text_idx_atstart(elim_word)
        keep_word.mergeWord(elim_word)
        self.update_all_spans(elim_idx, -1)

    def replace_word_text(self, word, old_text, new_text):
        old_text = word.text if old_text == "<all>" else old_text
        inc = len(new_text) - len(old_text)
        if inc != 0:
            if new_text == '':
                inc -= 1 # for space, as the word would be skipped.

            word_pos = self.get_text_idx_atstart(word)
            #word_pos += len(word.text)
            self.update_all_spans(word_pos, inc)
        word.replaceStr(old_text, new_text)

    def add_span(self, start, end, label, text_config=None):
        assert label and (start < end)
        rm_labels = text_config.rm_labels if text_config else []
        rm_spans = self.get_non_overlap_spans(rm_labels)

        if rm_spans:
            start_inc, end_inc = 0, 0
            new_spans = []
            for rm_span in rm_spans:
                if rm_span.start <= start and rm_span.start < end:
                    start_inc += len(rm_span)
                    end_inc += len(rm_span)
                elif rm_span.start < end:
                    #Added span is spanning an existing rm label span
                    end_inc += len(rm_span)
                    new_spans.append(Span(start=start + start_inc, end=rm_span.start, label=label))
                    new_spans.append(Span(start=rm_span.end, end=end+end_inc, label=label))
                    break
                else:
                    #Added span is before an existing rm label span
                    pass
            # end for
            if not new_spans:
                new_spans.append(Span(start=start + start_inc, end=end + end_inc, label=label))

            for new_span in new_spans:
                self.label_spans.setdefault(label, []).append(new_span)
        else:
            new_span = Span(start=start, end=end, label=label)
            self.label_spans.setdefault(label, []).append(new_span)

    # def line_text(self):
    #     # lines, word_char_idxs = self._build_line_text()
    #     # return '\n'.join(lines)
    #     return self.line_text2()

    # def line_text_no_nl(self):
    #     # lines, word_char_idxs = self._build_line_text()
    #     # return ' '.join(lines).replace('\n', ' ')
    #     return self.line_text2(TextConfig(rm_nl=True))

    @property
    def shape(self):
        if self.shape_ is None:
            self.shape_ = Shape.build_box([w.box for w in self.words])
        return self.shape_

    @property
    def xmin(self):
        return self.shape.xmin

    @property
    def xmax(self):
        return self.shape.xmax

    @property
    def ymin(self):
        return self.shape.ymin

    @property
    def ymax(self):
        return self.shape.ymax


    def reduce_width_at(self, direction, ov_shape):
        # reduce with only of the box
        assert direction in ("left", "right")
        box = self.shape.box

        #print(f'Reducing width words[0] {self.words[0].text} self:{box} ov:{ov_shape}')

        if direction == "left":
            assert self.xmin <= ov_shape.xmax
            new_top = Coord(x=ov_shape.xmax + 0.000001, y=box.top.y)
            self.shape.box.update_coords([new_top, self.shape.box.bot])
        else:
            assert self.xmax >= ov_shape.xmin
            new_bot = Coord(x=ov_shape.xmin - 0.000001, y=box.bot.y)
            self.shape.box.update_coords([self.shape.box.top, new_bot])



            
        # b /Users/mukund/Software/docInt/docint/region.py:84

    # def _build_line_text(self):
    #     lines, char_count, word_char_idxs = [], 0, []
    #     for line_idx, word_line in self.iter_word_lines():
    #         word_line = [w for w in word_line if w]
    #         for word in word_line:
    #             end_char = char_count + len(word.text)
    #             word_char_idxs.append((word, (char_count, end_char)))
    #             char_count = end_char + 1
    #         lines.append(' '.join([w.text for w in word_line]))
    #         #char_count += 1
    #     #print(f'*** {len(self)} -> {len(word_char_idxs)}')
    #     return lines, word_char_idxs

    # def blank_line_text_no_nl(self, s, e):
    #     lines, word_char_idxs = self._build_line_text()

    #     for (word, (start_char, end_char)) in word_char_idxs:
    #         #print(f'{word.text} [{start_char}:{end_char}]')
    #         if (start_char <= s <= end_char) or (start_char <= e <= end_char) or \
    #            (s <= start_char <= end_char <= e):
    #             #print(f'\tFound It {word.text} [{start_char}:{end_char}]')
    #             r_start, r_end = max(s, start_char), min(e, end_char)
    #             replace_str = word.text[r_start - start_char: r_end - start_char]
    #             word.replaceStr(replace_str, ' '*len(replace_str))
    #         elif start_char > e:
    #             break

    # def iter_word_lines(self):
    #     for line_idx, line in enumerate(self.word_lines):
    #         if line:
    #             yield line_idx, line

    # def iter_word_lines_words(self):
    #     for word_line in self.word_lines:
    #         for word in word_lines:
    #             yield word

    # @property
    # def text(self):
    #     if self.text_ is None:
    #         self.text_ = ' '.join([w.text for w in self.words])
    #     return self.text_
