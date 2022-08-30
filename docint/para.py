import re
import sys
from itertools import chain
from string import punctuation
from textwrap import wrap
from typing import Dict, Iterable, List

from enchant.utils import levenshtein
from pydantic import BaseModel
from rich import print as rprint
from rich.text import Text

from .region import MergeWordEdit, Region
from .span import Span, SpanGroup


class TextConfig(BaseModel):
    rm_labels: List[str] = []


class Para(Region):
    label_spans: Dict[str, List[Span]] = {}

    @classmethod
    def build_with_lines(cls, words, word_lines):
        word_idxs = [w.word_idx for w in words]
        page_idx = words[0].page_idx if words else None
        word_lines_idxs = [[w.word_idx for w in wl] for wl in word_lines]

        return Para(
            words=words,
            word_lines=word_lines,
            word_idxs=word_idxs,
            page_idx_=page_idx,
            word_lines_idxs=word_lines_idxs,
        )

    ## Display methods
    def str_spans(self, indent=""):
        t = self.line_text()
        label_strs = []
        for label, spans in self.label_spans.items():
            spanStrs = [f"[{s.start}:{s.end}]=>{t[s.start:s.end]}<" for s in spans]
            label_strs.append(f'{indent}{label}: {" ".join(spanStrs)}')
        return "\n".join(label_strs)

    def iter_word_span_idxs(self):
        # not sure about this
        start_pos = 0
        for line_idx, word_line in enumerate(self.word_lines):
            # first_word = True
            for pos_idx, word in enumerate(w for w in word_line if w.text):
                end_pos = start_pos + len(word)
                yield word, Span(start=start_pos, end=end_pos), line_idx, pos_idx
                start_pos += len(word) + 1

    def iter_word_text_idxs(self, text_config):
        # will include partial text, but not empty word
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        rm_spans = Span.accumulate(rm_spans)
        rm_span_group = SpanGroup(spans=rm_spans, text="")

        for word, word_span, line_idx, pos_idx in self.iter_word_span_idxs():
            o_type, o_span = rm_span_group.overlap_type(word_span)
            if o_type == "none":
                yield word, word.text, line_idx, pos_idx

            elif o_type == "partial":
                (s, e) = (
                    (o_span.end, word_span.end) if o_span.start == word_span.start else (word_span.start, o_span.start)
                )
                s, e = s - word_span.start, e - word_span.start
                yield word, word.text[s:e], line_idx, pos_idx

    def iter_adjoin_words_texts(self, text_config):
        def is_adjoin(prev_line_idx, prev_pos_idx, line_idx, pos_idx):
            return prev_line_idx == line_idx and prev_pos_idx + 1 == pos_idx

        prev_word, prev_text, prev_line_idx, prev_pos_idx = None, None, None, None
        for word, text, line_idx, pos_idx in self.iter_word_text_idxs(text_config):

            if (prev_line_idx is not None) and line_idx != prev_line_idx and prev_word:
                yield prev_word, None, prev_text, ""

            elif prev_word and is_adjoin(prev_line_idx, prev_pos_idx, line_idx, pos_idx):
                yield prev_word, word, prev_text, text
            prev_word, prev_text, prev_line_idx, prev_pos_idx = (
                word,
                text,
                line_idx,
                pos_idx,
            )
        yield prev_word, None, prev_text, ""

    # Temporary
    def iter_word_pairs(self, text_config=None):
        for word, n_word, _, _ in self.iter_adjoin_words_texts(text_config):
            yield word, n_word

    # Temporary
    def iter_words(self, text_config=None):
        for word, _, _, pos_idx in self.iter_word_text_idxs(text_config):
            yield pos_idx, word

    # Temporary, Why ? it is very convenient
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
                # Added span is spanning an existing rm label span
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
            return list(chain(*[self.label_spans.get(lb, []) for lb in labels]))

    def get_text_for_spans(self, spans):
        text = self.line_text()
        if isinstance(spans, Iterable):
            return ",".join(f"{text[s.slice()]}" for s in spans)
        else:
            span = spans
            return text[span.slice()]

    def get_words_in_spans(self, spans):
        overlap_words = []
        for word, word_span, line_idx, pos_idx in self.iter_word_span_idxs():
            if word_span.overlaps_any(spans):
                overlap_words.append(word)
        return overlap_words

    def line_text(self, text_config=None):
        word_texts = [w.text for wl in self.word_lines for w in wl if w]
        line_text = " ".join(word_texts)

        if text_config is None:
            return line_text

        if text_config.rm_nl:
            line_text.replace("\n", " ")

        # print(f"Line: {line_text}")

        line_text = list(line_text)
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        for rm_span in Span.accumulate(rm_spans):
            # print(f"start: {rm_span.start} end: {rm_span.end} label: {rm_span.label}")
            line_text[rm_span.start : rm_span.end] = "|" * len(rm_span)  # noqa: E203

        line_text = "".join(line_text)
        return line_text.replace("|", "")

    def word_idxs_line_text(self, text_config=None):
        def idx_text(w):
            idx, ln = w.word_idx, len(w.text)
            if len(str(idx)) <= ln:
                return "{0:{1}}".format(str(idx), ln)
            else:
                return " " * ln

        word_texts = [idx_text(w) for wl in self.word_lines for w in wl if w]
        line_text = " ".join(word_texts)

        if text_config is None:
            return line_text

        if text_config.rm_nl:
            line_text.replace("\n", " ")

        # print(f"Line: {line_text}")

        line_text = list(line_text)
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        for rm_span in Span.accumulate(rm_spans):
            # print(f"start: {rm_span.start} end: {rm_span.end} label: {rm_span.label}")
            line_text[rm_span.start : rm_span.end] = "|" * len(rm_span)  # noqa: E203

        line_text = "".join(line_text)
        return line_text.replace("|", "")

    def _fix_text(self, text):
        if not text.isascii():
            sys.stderr.write(f"{text}\n")
        text = text.strip()

        punct_tbl = str.maketrans(punctuation, " " * len(punctuation))
        text = text.translate(punct_tbl).strip()
        return text

    def is_correctable(self, text, dictionary):
        suggestions = dictionary.suggest(text)
        if not suggestions:
            return False
        lv_dist_cutoff = 1

        top_suggestion = suggestions[0].lower()
        lv_dist = levenshtein(top_suggestion, text.lower())
        # print(f'\t{text}->{suggestions[0]} {lv_dist}')

        if lv_dist <= lv_dist_cutoff or top_suggestion.startswith(text.lower()):
            return True
        else:
            return False

    def is_mergeable(self, text, next_word, dictionary):
        if next_word is None:
            return False

        next_text = self._fix_text(next_word.text)
        if not next_text:
            return False

        merged_text = text + next_text
        if dictionary.check(merged_text):
            # self.lgr.debug(f"MergeFound >{text}+{next_text}<")
            return True
        elif self.is_correctable(merged_text, dictionary):
            # self.lgr.debug(f"MergeCorrected {merged_text}")
            return True
        else:
            # print(f"Merge NotFound {merged_text}")
            return False

    def merge_words(self, dictionary, text_config=None):
        merge_count = 0

        if len(self.words) == 0:
            return

        last_merged_word, merge_words = None, []  # don't alter spans while iterating
        for word, next_word in self.iter_word_pairs(text_config):

            if (not word) or (not next_word) or (id(word) == id(last_merged_word)):
                continue

            text = self._fix_text(word.text)

            if not text:
                continue

            if self.is_mergeable(text, next_word, dictionary):
                # self.lgr.debug(f'Merged: {word.text} {next_word.text}')
                merge_words.append((word, next_word))
                merge_count += 1
                last_merged_word = next_word

        [self.merge_word(word, next_word) for (word, next_word) in merge_words]
        return merge_count

    def correct_words(self, dictionary, text_config=None):
        correct_count = 0
        replace_words = []  # don't alter spans while iterating
        for text, word in self.iter_word_text(text_config):
            text = self._fix_text(text)
            if not word or not text:
                continue

            if dictionary.check(text):
                continue

            if len(text) <= 2:
                if text in ("uf", "cf", "qf", "nf", "af", "bf"):
                    replace_words.append((word, "of"))
                    # self.lgr.debug(f"SpellCorrected {text} -> of")
                    correct_count += 1
                else:
                    pass
            elif self.is_correctable(text, dictionary):
                suggestions = dictionary.suggest(text)
                # self.lgr.debug(f"SpellCorrected {text} -> {suggestions[0]}")
                replace_words.append((word, suggestions[0]))
                correct_count += 1
            else:
                pass
                # self.lgr.debug(f"SpellNOTFOUND {text}")
        [self.replace_word_text(w, "<all>", t) for (w, t) in replace_words]
        return correct_count

    def mark_regex(self, regexes, label, text_config=None):
        line_text = self.line_text(text_config)
        new_spans = []
        for regex in regexes:
            for m in re.finditer(regex, line_text):
                new_spans.append(m.span())
        new_spans.sort(reverse=True)
        for (s, e) in new_spans:
            self.add_span(s, e, label, text_config)

    def print_color(self, error_type, color_config):
        line_text = self.line_text()
        color_text = Text(error_type + line_text)
        elen = len(error_type)
        for label, spans in self.label_spans.items():
            color = color_config.get(label, None)
            if color:
                [color_text.stylize(color, s.start + elen, s.end + elen) for s in spans]
        # end for
        rprint(color_text)

    def print_color_idx(self, color_config, width=90):
        line_text, idx_text = self.line_text(), self.word_idxs_line_text()
        wrap_texts = wrap(line_text, width=width, drop_whitespace=False)
        wrap_spans, start_pos = [], 0

        # flatten label->List[Spans] to label->Span
        label_spans = [(lb, s) for lb, ss in self.label_spans.items() for s in ss]
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
        # end for

        start_pos = 0
        for (w_text, w_spans) in zip(wrap_texts, wrap_spans):
            color_text = Text(w_text)
            for label, w_span in w_spans:
                color = color_config.get(label, None)
                if color:
                    color_text.stylize(color, w_span.start, w_span.end)
            rprint(color_text)
            print(idx_text[start_pos : start_pos + len(w_text)])  # noqa: E203
            start_pos += len(w_text) + 1

    def update_all_spans(self, text_idx, inc):
        [s.update(text_idx, inc) for spans in self.label_spans.values() for s in spans]

    def get_unlabeled_texts(self):
        line_text = self.line_text()
        all_spans = Span.accumulate(list(chain(*self.label_spans.values())))
        ts = Span.unmatched_texts(all_spans, line_text)
        return [s for t in ts for s in t.strip().split()]

    def merge_word(self, keep_word, elim_word):
        assert len(keep_word) != 0 and len(elim_word) != 0

        self.edits.append(MergeWordEdit.build(keep_word, elim_word))
        elim_pos = self.get_start_pos_word(elim_word)
        keep_word.mergeWord(elim_word)
        self.update_all_spans(elim_pos, -1)
