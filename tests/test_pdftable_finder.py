import pytest

import docint

docker_config = {
    "is_recognizer": True,
    "delete_container_dir": False,
}


@pytest.mark.skip(
    reason="don't want to install pdfplumber, in docker hard to copy both pdf and doc.json file"
)
def test_pdftable_finder(table_path):
    ppln = docint.empty(
        config={"docker_pipes": ["pdftable_finder"], "docker_config": docker_config}
    )  # TODO not able to find pdf
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("pdftable_finder", pipe_config={"num_columns": 4, "heading_offset": 0})
    doc = ppln(table_path)

    assert len(doc.pages[0].tables[0].body_rows) == 9
    assert len(doc.pages[0].tables[0].body_rows[0].cells) == 4

    assert doc.pages[0].tables[0].body_rows[4].cells[0].raw_text() == "5"
    assert doc.pages[0].tables[0].body_rows[4].cells[2].raw_text() == "80"
    assert doc.pages[0].tables[0].body_rows[4].cells[3].raw_text() == "5.2 AU"

    assert doc.pages[0].tables[0].header_rows[0].cells[0].raw_text() == "Number"

    assert doc.pages[0].heading.raw_text() == "Solar System Information"
