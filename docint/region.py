from typing import List, Dict, Iterable
from itertools import zip_longest, groupby, chain
from collections import Counter
from textwrap import wrap

from pydantic import BaseModel

from rich.text import Text
from rich import print as rprint


from .word import Word
from .shape import Shape, Box, Coord
from .span import Span, SpanGroup

class DataError(BaseModel):
    path: str
    msg: str

    def __str__(self):
        return f'{self.name}: {self.msg}'

    @property
    def name(self):
        return type(self).__name__

    @classmethod
    def error_counts(cls, errors):
        ctr = Counter(e.name for e in errors)
        return ' '.join(f'{n}:{ct}' for n, ct in ctr.most_common(None))


class DataEdit(BaseModel):
    msg: str

    def __str__(self):
        return self.msg

class MergeWordEdit(DataEdit):
    keep_word_path: str        
    elim_word_path: str
    elim_word_text: str
    keep_word_text: str

    @classmethod
    def build(cls, keep_word, elim_word):
        w1, w2 = keep_word, elim_word
        t1, t2 = w1.text, w2.text
        msg = f'{t1}<->{t2}'
        return MergeWordEdit(keep_word_path=w1.path, elim_word_path=w2.path,
                              keep_word_text=t1, elim_word_text=t2, msg=msg)


class ReplaceTextEdit(DataEdit):
    word_path: str
    old_text: str
    new_text: str

    @classmethod
    def build(cls, word, old_text, new_text):
        old_wtext = word.text
        msg = f'{old_wtext}->{old_wtext.replace(old_text, new_text)}'
        return ReplaceTextEdit(word_path=word.path, old_text=old_text,
                               new_text=new_text, msg=msg)


class TextConfig(BaseModel):
    rm_labels: List[str] = []
    rm_nl: bool = True


class Region(BaseModel):
    words: List[Word]
    text_: str = None
    shape_: Box = None
    word_lines: List[List[Word]] = None
    label_spans: Dict[str, List[Span]] = {}
    errors: List[DataError] = []
    edits: List[DataEdit] = []


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

    def get_regions(self):
        return [ self ]

    @property
    def error_counts_str(self):
        ctr = Counter(e.name for e in self.errors)
        return ' '.join(f'{n}:{ct}' for n, ct in ctr.most_common(None))

    def str_spans(self, indent=''):
        t = self.line_text()
        label_strs = []
        for label, spans in self.label_spans.items():
            spanStrs = [f'[{s.start}:{s.end}]=>{t[s.start:s.end]}<' for s in spans]
            label_strs.append(f'{indent}{label}: {" ".join(spanStrs)}')
        return '\n'.join(label_strs)

    def text_len(self):
        # should we eliminate zero words ? not now
        text_lens = [len(w.text) for w in self.words]
        num_spaces = len(text_lens) - 1
        return sum(text_lens) + num_spaces if text_lens else 0

    def text_isalnum(self):
        # should we eliminate zero words ? not now
        return all([w.text.isalnum() for w in self.words])

    def iter_word_span_idxs(self):
        start_pos = 0
        for line_idx, word_line in enumerate(self.word_lines):
            first_word = True
            for pos_idx, word in enumerate(w for w in word_line if w.text):
                end_pos = start_pos + len(word)
                yield word, Span(start=start_pos, end=end_pos), line_idx, pos_idx
                start_pos += len(word) + 1
    
    def iter_word_text_idxs(self, text_config):
        # will include partial text, but not empty word
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        rm_spans = Span.accumulate(rm_spans)
        rm_span_group = SpanGroup(spans=rm_spans, text='')
        
        for word, word_span, line_idx, pos_idx in self.iter_word_span_idxs():
            o_type, o_span = rm_span_group.overlap_type(word_span)
            if o_type == 'none':
                yield word, word.text, line_idx, pos_idx

            elif o_type == 'partial':
                (s, e) = (o_span.end, word_span.end) if o_span.start == word_span.start else (word_span.start, o_span.start)
                s, e = s-word_span.start, e-word_span.start
                yield word, word.text[s:e], line_idx, pos_idx

    def iter_adjoin_words_texts(self, text_config):
        def is_adjoin(prev_line_idx, prev_pos_idx, line_idx, pos_idx):
            return prev_line_idx == line_idx and prev_pos_idx + 1 == pos_idx
        
        prev_word, prev_text, prev_line_idx, prev_pos_idx = None, None, None, None
        for word, text, line_idx, pos_idx in self.iter_word_text_idxs(text_config):
            
            if (prev_line_idx is not None) and line_idx != prev_line_idx and prev_word:
                yield prev_word, None, prev_text, ''
                
            elif prev_word and is_adjoin(prev_line_idx, prev_pos_idx, line_idx, pos_idx):
                yield prev_word, word, prev_text, text
            prev_word, prev_text, prev_line_idx, prev_pos_idx = word, text, line_idx, pos_idx
        yield prev_word, None, prev_text, ''

    ## Temporary
    def iter_word_pairs(self, text_config=None):
        for word, n_word, _, _ in self.iter_adjoin_words_texts(text_config):
            yield word, n_word

    ## Temporary
    def iter_words(self, text_config=None):
        for word, _, _, pos_idx in self.iter_word_text_idxs(text_config):
            yield pos_idx, word

    ## Temporary
    def iter_word_text(self, text_config=None):
        for word, word_text, _, _ in self.iter_word_text_idxs(text_config):
            yield word_text, word

    def get_start_pos_word(self, edit_word):
        for word, word_span, line_idx, pos_idx in self.iter_word_span_idxs():
            if edit_word.word_idx == word.word_idx:
                return word_span.start

    def add_span(self, start, end, label, text_config=None):
        assert label and (start < end)

        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        rm_spans = Span.accumulate(rm_spans)

        new_spans, spanning_existing_span = [], False
        for rm_span in rm_spans:
            if rm_span.start <= start and rm_span.start < end:
                start += len(rm_span)
                end += len(rm_span)
            elif rm_span.start < end:
                #Added span is spanning an existing rm label span
                new_spans.append(Span(start=start, end=rm_span.start))
                new_spans.append(Span(start=rm_span.end, end=end + len(rm_span)))
                spanning_existing_span = True
                break

        if not spanning_existing_span:
            new_spans.append(Span(start=start, end=end))

        for new_span in new_spans:
            self.label_spans.setdefault(label, []).append(new_span)
            
    def get_spans(self, labels):
        if isinstance(labels, str):        
            return self.label_spans.get(labels, [])
        else:
            return list(chain(*[ self.label_spans.get(l, []) for l in labels ]))            

    def get_text_for_spans(self, spans):
        text = self.line_text()        
        if isinstance(spans, Iterable):
            return ','.join(f'{text[s.slice()]}' for s in spans)
        else:
            return text[span.slice()]

    def get_words_in_spans(self, spans):
        overlap_words = []
        for word, word_span, line_idx, pos_idx in self.iter_word_span_idxs():
            if word_span.overlaps_any(spans):
                overlap_words.append(word)
        return overlap_words

    def raw_text(self):
        word_texts = [w.text for w in self.words if w]
        return " ".join(word_texts)

    def orig_text(self):
        word_texts = [w.orig_text for wl in self.word_lines for w in wl if w.orig_text]
        return " ".join(word_texts)

    def line_text(self, text_config=None):
        word_texts = [w.text for wl in self.word_lines for w in wl if w]
        line_text = " ".join(word_texts)

        if text_config is None:
            return line_text

        if text_config.rm_nl:
            line_text.replace("\n", " ")

        #print(f"Line: {line_text}")

        line_text = list(line_text)
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        for rm_span in Span.accumulate(rm_spans):
            #print(f"start: {rm_span.start} end: {rm_span.end} label: {rm_span.label}")
            line_text[rm_span.start:rm_span.end] = "|" * len(rm_span)

        line_text = "".join(line_text)
        return line_text.replace("|", "")

    def word_idxs_line_text(self, text_config=None):
        def idx_text(w):
            idx, l = w.word_idx, len(w.text)
            if len(str(idx)) <= l:
                return '{0:{1}}'.format(str(idx), l)
            else:
                return ' ' * l
        
        word_texts = [ idx_text(w) for wl in self.word_lines for w in wl if w]
        line_text = " ".join(word_texts)

        if text_config is None:
            return line_text

        if text_config.rm_nl:
            line_text.replace("\n", " ")

        #print(f"Line: {line_text}")

        line_text = list(line_text)
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        for rm_span in Span.accumulate(rm_spans):
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


    def print_color_idx(self, color_config, width=90):
        line_text, idx_text = self.line_text(), self.word_idxs_line_text()
        wrap_texts = wrap(line_text, width=width, drop_whitespace=False)
        wrap_spans, start_pos = [], 0

        # flatten label->List[Spans] to label->Span
        label_spans = [(l, s) for l, ss in self.label_spans.items() for s in ss]
        for (line_idx, w_text) in enumerate(wrap_texts):
            line_span = Span(start=start_pos, end=start_pos + len(w_text))
            wrap_line_spans = []
            for label, span in label_spans:
                if line_span.overlaps(span):
                    new_start = max(span.start - start_pos, 0)
                    new_end = min(span.end - start_pos, len(w_text))
                    wrap_line_spans.append((label, Span(start=new_start, end=new_end)))
            wrap_spans.append(wrap_line_spans)
            start_pos += len(w_text) 
        #end for

        start_pos = 0
        for (w_text, w_spans) in zip(wrap_texts, wrap_spans):
            color_text = Text(w_text)
            for label, w_span in w_spans:
                color = color_config.get(label, None)
                if color:
                    color_text.stylize(color, w_span.start, w_span.end)
            rprint(color_text)
            print(idx_text[start_pos:start_pos+len(w_text)])
            start_pos += len(w_text) + 1
        
        
    def update_all_spans(self, text_idx, inc):
        [s.update(text_idx, inc) for spans in self.label_spans.values() for s in spans]

    def get_unlabeled_texts(self):
        line_text = self.line_text()
        all_spans = Span.accumulate(list(chain(*self.label_spans.values())))
        ts = Span.unmatched_texts(all_spans, line_text)
        return [ s for t in ts for s in t.strip().split()]

    def merge_word(self, keep_word, elim_word):
        assert len(keep_word) != 0 and len(elim_word) != 0

        self.edits.append(MergeWordEdit.build(keep_word, elim_word))
        elim_pos = self.get_start_pos_word(elim_word)
        keep_word.mergeWord(elim_word)
        self.update_all_spans(elim_pos, -1)

    def replace_word_text(self, word, old_text, new_text):
        old_text = word.text if old_text == "<all>" else old_text
        inc = len(new_text) - len(old_text)
        self.edits.append(ReplaceTextEdit.build(word, old_text, new_text))
        if inc != 0:
            if new_text == '':
                inc -= 1 # for space, as the word would be skipped.

            word_pos = self.get_start_pos_word(word)
            self.update_all_spans(word_pos, inc)
        word.replaceStr(old_text, new_text)

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
