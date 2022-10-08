from pathlib import Path

import pytest

import docint
from docint.vocab import Vocab


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


@pytest.fixture
def mis_spelt_doc():
    return build_doc("mis_spelt.pdf")


@pytest.fixture
def paren_doc():
    return build_doc("paren.pdf")


@pytest.fixture
def mis_spelt_multi_line_doc():
    return build_doc("mis_spelt_multi_line.pdf")


@pytest.fixture
def multi_merge_doc():
    return build_doc("multi_merge.pdf")


@pytest.fixture
def numbered_list_doc():
    return build_doc("numbered_list.pdf")


@pytest.fixture
def numbered_list_path():
    return Path("tests/numbered_list.pdf")


@pytest.fixture
def layout_docs():
    return [build_doc(f'layout{i}.pdf') for i in range(1, 6)]


@pytest.fixture
def layout_more_docs():
    return [build_doc(f'layout{i}.pdf') for i in range(1, 11)]


@pytest.fixture
def layout_paths():
    return [Path('tests') / Path(f'layout{i}.pdf') for i in range(1, 6)]


@pytest.fixture
def layout_more_paths():
    return [Path('tests') / Path(f'layout{i}.pdf') for i in range(1, 11)]


@pytest.fixture
def insensitive_vocab():
    text = 'The quick brown fox jumped over the LAZY Fox.'
    texts = [t.strip(' .').lower() for t in text.split()]
    return Vocab(texts)


@pytest.fixture
def sensitive_vocab():
    text = 'The quick brown fox jumped over the LAZY Fox.'
    texts = [t.strip(' .') for t in text.split()]
    return Vocab(texts, case_sensitive=True)


@pytest.fixture
def images_path():
    return Path('tests') / 'images.pdf'


@pytest.fixture
def table_path():
    return Path('tests') / 'table.pdf'


@pytest.fixture
def table_nolines_path():
    return Path('tests') / 'table_nolines.pdf'
