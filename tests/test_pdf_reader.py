from pathlib import Path

import pytest

import docint


@pytest.mark.parametrize(
    "pdf_path, word_count",
    [
        ("one_word.pdf", 1),
        ("one_line.pdf", 9),
        ("two_pages.pdf", 22),
        ("numbered_list.pdf", 180),
    ],
)
def test_word_count(pdf_path, word_count):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    doc = ppln(Path("tests") / pdf_path)
    total_words = sum(len(p.words) for p in doc.pages)
    # [ print(f'{idx}: {w.text}') for (idx, w) in enumerate(doc[0].words)]
    assert total_words == word_count


@pytest.mark.parametrize(
    "pdf_path, word_text",
    [
        ("one_line.pdf", "over"),
        ("two_pages.pdf", "over"),
        ("numbered_list.pdf", "jumped"),
    ],
)
def test_word_text(pdf_path, word_text):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    doc = ppln(Path("tests") / pdf_path)
    assert doc.pages[0].words[5].text == word_text
