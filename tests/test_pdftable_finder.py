import docint


def test_pdftable_finder(table_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("pdftable_finder", pipe_config={"num_columns": 4})
    doc = ppln(table_path)

    assert len(doc.pages[0].tables[0].body_rows) == 9
    assert len(doc.pages[0].tables[0].body_rows[0].cells) == 4

    assert doc.pages[0].tables[0].body_rows[4].cells[0].raw_text() == "5"
    assert doc.pages[0].tables[0].body_rows[4].cells[2].raw_text() == "80"
    assert doc.pages[0].tables[0].body_rows[4].cells[3].raw_text() == "5.2 AU"

    assert doc.pages[0].tables[0].header_rows[0].cells[0].raw_text() == "Number"

    assert doc.pages[0].heading.raw_text() == "Solar System Information"
