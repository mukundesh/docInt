from pathlib import Path

import pytest

from docint.ppln import Pipeline


def test_ppln_file_name(one_line_path):
    ppln = Pipeline.from_config({"pipeline": ["AddFileName"]})
    one_line_doc = ppln(one_line_path)
    assert one_line_doc.extract_file_name == "one_line.pdf"


def test_ppln_files(layout_paths):
    ppln = Pipeline.from_config({"pipeline": ["AddFileName"]})
    layout_docs = ppln(layout_paths)
    for doc in layout_docs:
        print(doc.pdf_name)


def test_ppln_files_ignore(layout_paths):
    ppln = Pipeline.from_config({"pipeline": ["AddFileName"], "ignore_docs": ["layout2.pdf"]})
    layout_docs = ppln(layout_paths)
    assert len(list(layout_docs)) == len(layout_paths) - 1


def test_ppln_files_config(layout_paths):
    ppln = Pipeline.from_config({"pipeline": ["AddFileName"], "config_dir": "tests/core"})

    config_file_path = Path("tests") / "core" / Path("layout4.pdf.addfilename.yml")
    config_file_path.write_text("make_upper_case: True")
    layout_docs = list(ppln(layout_paths))
    config_file_path.unlink()

    assert layout_docs[0].extract_file_name == "layout1.pdf"
    assert layout_docs[3].extract_file_name == "LAYOUT4.PDF"
