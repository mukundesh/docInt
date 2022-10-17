import docint


def test_table_builder_edges(table_nolines_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("num_marker")
    ppln.add_pipe("list_finder")
    ppln.add_pipe("table_finder")
    doc = ppln(table_nolines_path)

    assert len(doc.pages[0].tables[0].body_rows) == 9
    assert len(doc.pages[0].tables[0].body_rows[0].cells) == 3

    assert doc.pages[0].tables[0].body_rows[4].cells[0].raw_text() == "5"
    assert doc.pages[0].tables[0].body_rows[4].cells[1].raw_text() == "Jupiter"
