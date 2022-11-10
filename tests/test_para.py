import pdb  # noqa

import pytest

from docint.para import Para, TextConfig
from docint.span import Span

# Texts    : The quick brown fox jumped over the lazy fox.
# pos_idxs : 0   4     10    16  20     27   32  36   41
# word_idxs: 0   1     2     3   4      5    6   7    8


def test_labels(one_line_doc):
    all_words = one_line_doc.pages[0].words
    para = Para.build_with_lines(all_words, [all_words])

    para.add_label(Span(start=16, end=19), "animal")
    para.add_label(Span(start=41, end=44), "animal")

    para.add_label(Span(start=4, end=9), "speed")
    para.add_label(Span(start=36, end=40), "speed")
    no_labels = TextConfig(rm_labels=["animal", "speed"])
    no_labels_text = "The brown jumped over the ."

    assert para.line_text(no_labels) == no_labels_text

    no_animal = TextConfig(rm_labels=["animal"])
    speed2_spans = [Span(start=4, end=9), Span(start=32, end=36)]
    para.add_label(speed2_spans, "speed2", no_animal)

    no_animal_speed2 = TextConfig(rm_labels=["animal", "speed2"])
    assert para.line_text(no_animal_speed2) == no_labels_text

    para.add_label(Span(start=11, end=13), "partial")  # ro in brown
    para.add_label(Span(start=20, end=23), "partial")  # jum in jumped
    para.add_label(Span(start=29, end=31), "partial")  # er in over

    no_animal_partial = "The quick bwn ped ov the lazy ."
    no_animal_partial_tc = TextConfig(rm_labels=["animal", "partial"])
    assert para.line_text(no_animal_partial_tc) == no_animal_partial

    para.add_label(Span(start=25, end=29), "speed3", no_animal_partial_tc)

    no_animal_partial_speed3_tc = TextConfig(rm_labels=["animal", "partial", "speed3"])
    no_animal_partial_speed3 = "The quick bwn ped ov the ."
    assert para.line_text(no_animal_partial_speed3_tc) == no_animal_partial_speed3


def test_partial(one_line_doc):
    all_words = one_line_doc.pages[0].words
    para = Para.build_with_lines(all_words, [all_words])

    para.add_label(Span(start=24, end=25), "partial_one_word")  # m
    para.add_label(Span(start=22, end=23), "partial_one_word")  # p

    no_partial_one_word = TextConfig(rm_labels=["partial_one_word"])
    assert para.line_text(no_partial_one_word) == "The quick brown fox jupd over the lazy fox."

    para.add_label(Span(start=20, end=23), "partial_one_word")  # p
    assert para.line_text(no_partial_one_word) == "The quick brown fox pd over the lazy fox."

    no_partial_two_words = TextConfig(rm_labels=["partial_two_words"])
    para.add_label(Span(start=22, end=29), "partial_two_words")
    assert para.line_text(no_partial_two_words) == "The quick brown fox juer the lazy fox."

    no_partial_span_three_words = TextConfig(rm_labels=["partial_span_three_words"])
    para.add_label(Span(start=22, end=33), "partial_span_three_words")
    assert para.line_text(no_partial_span_three_words) == "The quick brown fox juhe lazy fox."


def test_overlapping(one_line_doc):
    all_words = one_line_doc.pages[0].words
    para = Para.build_with_lines(all_words, [all_words])

    para.add_label(Span(start=32, end=35), "article")
    no_article_config = TextConfig(rm_labels=["article"])
    no_article_line = para.line_text(TextConfig(rm_labels=["article"]))
    assert no_article_line == "The quick brown fox jumped over lazy fox."

    para.add_label(Span(start=27, end=36), "overlap", no_article_config)
    overlap_line = para.line_text(TextConfig(rm_labels=["article", "overlap"]))
    assert overlap_line == "The quick brown fox jumped fox."

    para.add_label(Span(start=24, end=28), "article")
    para.add_label(Span(start=10, end=40), "overlap")

    new_overlap_line = para.line_text(TextConfig(rm_labels=["article", "overlap"]))
    assert new_overlap_line == "The quick fox."


# mis_spelt_doc
# Text: A qu ick bromn fox jumbed ov9r the l azy fox.


def test_edits(mis_spelt_doc, insensitive_vocab):
    all_words = mis_spelt_doc.pages[0].words
    para = Para.build_with_lines(all_words, [all_words])
    vocab = insensitive_vocab

    para.merge_words(vocab, dist_cutoff=1)
    para.correct_words(vocab, dist_cutoff=1)
    assert para.text == "A quick brown fox jumped over the lazy fox."


def test_labels_edits(mis_spelt_doc, insensitive_vocab):
    doc, vocab = mis_spelt_doc, insensitive_vocab

    all_words = doc.pages[0].words
    para = Para.build_with_lines(all_words, [all_words])
    para.add_label(Span(start=0, end=1), "ignore")

    ignore_tc = TextConfig(rm_labels=["ignore"])

    para.merge_words(vocab, ignore_tc, dist_cutoff=1)
    para.correct_words(vocab, ignore_tc, dist_cutoff=1)
    # print(para.line_text(ignore_tc))

    assert para.line_text(ignore_tc) == "quick brown fox jumped over the lazy fox."


def test_paren(paren_doc, insensitive_vocab):
    doc, vocab = paren_doc, insensitive_vocab

    all_words = doc.pages[0].words
    para = Para.build_with_lines(all_words, [all_words])

    r = r"\((.*?)\)"
    para.label_regex(r, "ignore")

    paren_tc = TextConfig(rm_labels=["ignore"])
    para.merge_words(vocab, paren_tc, dist_cutoff=0)
    print(f"After Merge: {para.line_text(paren_tc)}\n")

    para.correct_words(vocab, paren_tc, dist_cutoff=1)
    print(f"After Correct: {para.line_text(paren_tc)}\n")

    assert para.line_text(paren_tc) == "The quick brown fox jumped over the l azyfok."


def test_multi_line(mis_spelt_multi_line_doc, insensitive_vocab):
    doc, vocab = mis_spelt_multi_line_doc, insensitive_vocab

    # this is fyi
    long_line = (
        "Line1: A quick brown fox jumped over the lazy fox. "
        "Line2: A quick brown fox jumped over the lazy fox. "
        "Line3: A quick brown fox jumped over the lazy fox. "
        "Line4: A quick brown fox jumped over the lazy fox."
    )

    # , all_words[12:24], all_words[24:36], all_words[36:48]])
    all_words = doc.pages[0].words
    para = Para.build_with_lines(
        all_words,
        [all_words[0:12], all_words[12:24], all_words[24:36], all_words[36:48]],
    )

    para.merge_words(vocab, dist_cutoff=1)
    para.correct_words(vocab, dist_cutoff=1)

    assert para.line_text() == long_line


@pytest.mark.skip(reason="multi merge is not working, will need more work, look at para.py.")
def test_multi_merge(multi_merge_doc, insensitive_vocab):
    doc, vocab = multi_merge_doc, insensitive_vocab

    all_words = doc.pages[0].words
    para = Para.build_with_lines(all_words, [all_words])

    para.merge_multi_words(vocab, 3, dist_cutoff=1)
    para.correct_words(vocab, dist_cutoff=1)

    print(para.line_text())
