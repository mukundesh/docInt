import pytest

from docint.ppln import Pipeline


def test_ppln_file_name(one_line_path):
    ppln = Pipeline.from_config({"pipeline": ["AddFileName"]})
    one_line_doc = ppln(one_line_path)
    assert one_line_doc.extract_file_name == "one_line.pdf"
