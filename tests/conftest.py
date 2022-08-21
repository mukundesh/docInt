from pathlib import Path

import pytest

import docint


def build_doc(file_name):
    if Path(file_name).exists():
        file_path = Path(file_name)
    else:
        file_path = Path(__file__).parent / file_name

    viz = docint.empty()
    viz.add_pipe("pdf_reader")
    doc = viz(file_path)
    return doc


@pytest.fixture
def one_word_doc():
    return build_doc("one_word.pdf")


@pytest.fixture
def one_line_doc():
    return build_doc("one_line.pdf")


@pytest.fixture
def two_lines_doc():
    return build_doc("two_lines.pdf")


@pytest.fixture
def two_pages_doc():
    return build_doc("two_pages.pdf")
