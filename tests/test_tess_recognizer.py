from pathlib import Path

import pytest

import docint

docker_config = {
    "is_recognizer": True,
    "delete_container_dir": False,
}


@pytest.mark.parametrize(
    "pdf_path, word_count, word_text",
    [
        ("one_word.pdf", 1, ""),
        ("one_line.pdf", 10, "over"),
        ("two_pages.pdf", 25, "over"),
    ],
)
def test_word_count(pdf_path, word_count, word_text):
    ppln = docint.empty(
        config={"docker_pipes": ["tess_recognizer2"], "docker_config": docker_config}
    )
    # ppln = docint.empty()
    ppln.add_pipe("tess_recognizer2")
    doc = ppln(Path("tests") / pdf_path)
    total_words = sum(len(p.words) for p in doc.pages)

    if total_words != word_count:
        [print(f"{idx}: {w.text}") for (idx, w) in enumerate(doc[0].words)]

    if word_text:
        assert doc.pages[0].words[5].text == word_text
