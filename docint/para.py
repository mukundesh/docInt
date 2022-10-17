import re
import sys
from string import punctuation
from typing import Dict, List

from more_itertools import first, flatten
from pydantic import BaseModel

from .region import Region
from .span import Span, SpanGroup, flatten_spans


class TextConfig(BaseModel):
    rm_labels: List[str] = []

    @classmethod
    def build(cls, labels):
        labels = labels if isinstance(labels, list) else [labels]
        return TextConfig(rm_labels=labels)


class Para(Region):
    label_spans: Dict[str, List[Span]] = {}
    t: str = None

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

    def __str__(self):
        s = f"Text: {self.text}\n"
        for label, spans in self.label_spans.items():
            s += f"\t{label}: {Span.to_str(self.text, spans)}\n"
        return s

    @property
    def text(self):
        if self.t is None:
            self.t = " ".join(w.text for wl in self.word_lines for w in wl if w.text)
        return self.t

    def iter_word_span_idxs(self):
        # not sure about this
        start_pos = 0
        for line_idx, word_line in enumerate(self.word_lines):
            # first_word = True
            for pos_idx, word in enumerate(w for w in word_line if w.text):
                end_pos = start_pos + len(word)
                yield word, Span(start=start_pos, end=end_pos), line_idx, pos_idx
                start_pos += len(word) + 1

    def iter_word_text_idxs_span(self, text_config):
        # will include partial text, but not empty word
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        rm_spans = Span.accumulate(rm_spans, text=self.text, ignore_chars=" ")
        rm_span_group = SpanGroup(spans=rm_spans, text="")

        for word, word_span, line_idx, pos_idx in self.iter_word_span_idxs():
            o_type, o_spans = rm_span_group.overlap_type2(word_span)
            if o_type == "none":
                yield word, word.text, line_idx, pos_idx, [word_span]

            elif o_type == "partial":
                non_o_spans = word_span.get_non_overlapping(o_spans)
                non_o_text = "".join(self.text[s.slice()] for s in non_o_spans)
                yield word, non_o_text, line_idx, pos_idx, non_o_spans

    def iter_adjoin_words_texts(self, text_config):
        def is_adjoin(prev_line_idx, prev_pos_idx, line_idx, pos_idx):
            return prev_line_idx == line_idx and prev_pos_idx + 1 == pos_idx

        prev_word, prev_text, prev_line_idx, prev_pos_idx = None, None, None, None
        for word, text, line_idx, pos_idx, _ in self.iter_word_text_idxs_span(text_config):

            if (prev_line_idx is not None) and line_idx != prev_line_idx and prev_word:
                yield prev_word, None, prev_text, ""

            elif prev_word and is_adjoin(prev_line_idx, prev_pos_idx, line_idx, pos_idx):
                yield prev_word, word, prev_text, text

            prev_word, prev_text = word, text
            prev_line_idx, prev_pos_idx = line_idx, pos_idx
        yield prev_word, None, prev_text, ""

    def iter_adjoin(self, adjoin_count, text_config):
        assert adjoin_count > 1

        def is_adjoin(prev_info, cur_info):
            return prev_info[2] == cur_info[2] and prev_info[3] + 1 == cur_info[3]

        def get_yield_pop_info(info_list):
            has_none = info_list.count(None) > 0
            if has_none:
                adjoin_idx = min(adjoin_count, info_list.index(None))
                if adjoin_idx > 1:
                    return info_list[:adjoin_idx], True
                else:
                    return None, True
            elif len(info_list) >= adjoin_count:
                return info_list[:adjoin_count], True
            else:
                return None, False

        info_list = []
        for word, text, line_idx, pos_idx, _ in self.iter_word_text_idxs_span(text_config):
            word_info = (word, text, line_idx, pos_idx)

            if (not info_list) or is_adjoin(info_list[-1], word_info):
                info_list.append(word_info)
            else:
                info_list.append(None)
                info_list.append(word_info)

            yield_list, pop_info = get_yield_pop_info(info_list)
            if yield_list:
                yield yield_list

            if pop_info:
                info_list.pop(0)

        while info_list:
            yield_list, _ = get_yield_pop_info(info_list)
            if yield_list:
                yield yield_list
            info_list.pop(0)

    def get_base_spans(self, span, text_config):
        rm_spans = self.get_spans(text_config.rm_labels) if text_config else []
        rm_spans = Span.accumulate(rm_spans, text=self.text, ignore_chars=" ")
        start, end = span.start, span.end

        base_spans, spanning_existing_span = [], False
        for rm_span in rm_spans:
            if rm_span.start <= start and rm_span.start < end:
                inc = 1 if rm_span.on_word_boundary(self.text) else 0
                start += len(rm_span) + inc
                end += len(rm_span) + inc
            elif rm_span.start < end:
                # Added span is spanning an existing rm label span
                base_spans.append(Span(start=start, end=rm_span.start))
                base_spans.append(Span(start=rm_span.end, end=end + len(rm_span)))
                spanning_existing_span = True
                break

        if not spanning_existing_span:
            base_spans.append(Span(start=start, end=end))

        return base_spans

    # def add_label(self, spans, label, text_config=None):
    #     [self.label_span(s, label, text_config) for s in flatten_spans(spans)]

    def add_label(self, span, label, text_config=None):
        base_spans = []
        for s in flatten_spans(span):
            base_spans += self.get_base_spans(s, text_config)

        outside_spans = [s for s in base_spans if s.in_boundary(self.text)]
        if outside_spans:
            o_span_str = Span.to_str(self.text, outside_spans)
            raise ValueError(f"Spans start/end in > < Spans: {o_span_str}")

        for new_span in base_spans:
            self.label_spans.setdefault(label, []).append(new_span)

    def label_regex(self, regexes, label, text_config=None):
        line_text = self.line_text(text_config)
        new_spans = []
        regexes = regexes if isinstance(regexes, list) else [regexes]
        for regex in regexes:
            for m in re.finditer(regex, line_text):
                new_spans.append(Span(start=m.span()[0], end=m.span()[1]))
        new_spans.sort(reverse=True)
        [self.add_label(s, label, text_config) for s in new_spans]

    def get_spans(self, labels):
        if isinstance(labels, str):
            return self.label_spans.get(labels, [])
        else:
            return list(flatten(self.label_spans.get(lb, []) for lb in labels))

    def get_text_for_spans(self, spans, text_config, boundary_char=" "):
        line_text = self.line_text(text_config)
        return boundary_char.join(line_text[s.slice()] for s in spans)

    def get_words_for_spans(self, spans, text_config):
        base_spans = self.get_base_spans(spans, text_config)

        overlap_words = []
        for word, word_span, _, _ in self.iter_word_span_idxs():
            if word_span.overlap_any(base_spans):
                overlap_words.append(word)
        return overlap_words

    def line_text(self, text_config=None):
        if not text_config:
            word_texts = [w.text for wl in self.word_lines for w in wl if w]
            return " ".join(word_texts)

        else:
            word_texts = []
            for _, text, _, _, _ in self.iter_word_text_idxs_span(text_config):
                if text:
                    word_texts.append(text)
            return " ".join(word_texts)

    def word_idxs_line_text(self, text_config=None):
        def idx_text(word, text):
            idx, ln = word.word_idx, len(text)
            if len(str(idx)) <= ln:
                return "{0:{1}}".format(str(idx), ln)
            else:
                return " " * ln

        idx_texts = []
        for word, text, _, _, _ in self.iter_word_text_idxs_span(text_config):
            if text:
                idx_texts.append(idx_text(word, text))

        return " ".join(idx_texts)

    def elim_punct(self, text):
        punct_tbl = str.maketrans(punctuation, " " * len(punctuation))
        text = text.translate(punct_tbl).strip()
        return text

    def check_language(self, text, language="en"):
        assert language == "en"
        if not text.isascii():
            sys.stderr.write(f"Unicode: {text}\n")
            return False
        return True

    def merge_words(self, vocab, text_config=None, dist_cutoff=1):
        last_merged_word, merge_words = None, []  # don't alter spans while iterating
        for word, next_word, text, next_text in self.iter_adjoin_words_texts(text_config):
            if (not word) or (not next_word) or (id(word) == id(last_merged_word)):
                continue

            if word.word_idx == next_word.word_idx:
                continue

            text = self.elim_punct(text)
            if vocab.has_text(text):
                continue

            next_text = self.elim_punct(next_text)

            if (not text) or (not next_text):
                continue

            merged_text = text + next_text
            if vocab.has_text(merged_text, dist_cutoff):
                print(f"\tMerging: {text} {next_text} -> {merged_text}")
                merge_words.append((word, next_word))
                last_merged_word = next_word

        [self.merge_word(word, next_word) for (word, next_word) in merge_words]
        self.t = None
        return len(merge_words)

    # PAUSING THE MULTI MERGE THREAD as merging words with single letters is difficult
    # as the words get eliminated in has_vocab_words example 'l' + 'azy', 'azy' is in
    # dictionary so does not get merged lazy. Similar problems 'A' + 'q'

    def merge_multi_words(self, vocab, adjoin_count, text_config=None, dist_cutoff=1):
        def is_mergeable(info_list):
            merge_text = "".join(info[1] for info in info_list)
            return vocab.has_text(merge_text, dist_cutoff)

        def has_vocab_words(info_list):
            for info in info_list:
                if vocab.has_text(info[1], dist_cutoff):
                    print(f"\t\tIN VOCAB {info[1]}")
                    return True
            return False

        merged_word_idxs, to_merge_words = set(), []
        for word_info_list in self.iter_adjoin(adjoin_count, text_config):
            print(f'Iterating: {", ".join(i[1] for i in word_info_list)}')

            # remove words that are already merged
            non_merged_word_list = []
            for idx, word_info in enumerate(word_info_list):
                if word_info[0].word_idx in merged_word_idxs:
                    continue
                else:
                    non_merged_word_list = word_info_list[idx:]
                    break

            # Only keep words that have text
            non_merged_word_list = [w for w in non_merged_word_list if w[1]]

            if len(non_merged_word_list) < 2:
                continue

            print(f'\tIterating-AfterRemoval: {", ".join(i[1] for i in non_merged_word_list)}')

            # check if the words exist in vocab
            for idx, word_info in enumerate(non_merged_word_list[:-1]):
                merge_slice = slice(0, len(non_merged_word_list) - idx)
                merge_list = non_merged_word_list[merge_slice]

                if has_vocab_words(merge_list):
                    # print(f'\tFound Vocab Word: {", ".join(i[1] for i in merge_list)}')
                    continue

                print(f'\tChecking: {", ".join(i[1] for i in merge_list)}')
                if is_mergeable(merge_list):
                    merge_words = [info[0] for info in merge_list]
                    print(f'\t\tMulti-merge: {"".join(i[1] for i in merge_list)}')
                    to_merge_words.append(merge_words)
                    assert all(w.word_idx not in merged_word_idxs for w in merge_words)

                    [merged_word_idxs.add(w.word_idx) for w in merge_words]

        [self.edit_merge_words(words) for words in to_merge_words]

    def correct_words(self, vocab, text_config=None, dist_cutoff=1):
        OF_TEXTS = ("uf", "cf", "qf", "nf", "af", "bf")
        replace_words = []  # don't alter spans while iterating
        for word, text, _, _, o_spans in self.iter_word_text_idxs_span(text_config):

            if text not in word.text:
                # not contiguous
                continue

            text = self.elim_punct(text)
            if not word or not text or text not in word.text:
                continue

            if vocab.has_text(text, dist_cutoff=0):
                continue

            if len(text) <= 2:
                if text in OF_TEXTS:
                    replace_words.append((word, "of"))
                else:
                    pass
            else:
                matched_texts = vocab.find_texts(text, dist_cutoff)
                if matched_texts:
                    print(f"\tFound correction: {text} {matched_texts[0][0]}")
                    new_text = word.text.replace(text, matched_texts[0][0])
                    replace_words.append((word, new_text))

        [self.replace_word_text(w, "<all>", t) for (w, t) in replace_words]
        self.t = None
        return len(replace_words)

    def update_all_spans(self, text_idx, inc):
        [s.update(text_idx, inc) for spans in self.label_spans.values() for s in spans]

    def merge_word(self, keep_word, elim_word):
        self.t = None
        assert len(keep_word) != 0 and len(elim_word) != 0
        elim_span = self.get_word_span(elim_word)
        keep_word.mergeWord(elim_word)
        self.update_all_spans(elim_span.start, -1)

    def edit_merge_words(self, words):
        self.t = None
        assert all(len(w) > 0 for w in words)
        assert len(words) > 1

        elim_span = self.get_word_span(words[1])
        [words[0].mergeWord(w) for w in words[1:]]
        inc = -1 * (len(words) - 1)
        self.update_all_spans(elim_span.start, inc)

    def replace_word_text(self, word, old_text, new_text):
        # correct words and make ascii
        old_text = word.text if old_text == "<all>" else old_text
        inc = len(new_text) - len(old_text)
        if inc != 0:
            if new_text == "":
                inc -= 1  # for space, as the word would be skipped.
            word_span = self.get_word_span(word)
            self.update_all_spans(word_span.start, inc)
        word.replaceStr(old_text, new_text)

    def get_unlabeled_texts(self):
        line_text = self.line_text()
        all_spans = Span.accumulate(list(flatten(self.label_spans.values())))
        ts = Span.unmatched_texts(all_spans, line_text)
        return [s for t in ts for s in t.strip().split()]

    def get_word_span(self, word):
        ws_iter = ((w, s) for w, s, _, _ in self.iter_word_span_idxs())
        return first((s for (w, s) in ws_iter if w.word_idx == word.word_idx), None)
