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
    para.merge_words(vocab, paren_tc, dist_cutoff=1)
    para.correct_words(vocab, paren_tc, dist_cutoff=1)

    assert para.line_text(paren_tc) == "The quick brown fox jumped over the lazy fox."
    assert para.text == "The quick brown fox jumped over the lazy(slow animal)fox."


def test_multi_line(mis_spelt_multi_line_doc, insensitive_vocab):
    doc, vocab = mis_spelt_multi_line_doc, insensitive_vocab

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
