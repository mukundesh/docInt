import docint


def test_table_builder_edges(table_path):
    ppln = docint.empty()
    ppln.add_pipe('pdf_reader')
    ppln.add_pipe('num_marker')
    ppln.add_pipe('table_edge_finder', pipe_config={'expected_columns': 4})
    ppln.add_pipe('table_builder_on_edges')
    doc = ppln(table_path)

    assert len(doc.pages[0].tables[0].body_rows) == 9
    assert len(doc.pages[0].tables[0].body_rows[0].cells) == 4

    assert doc.pages[0].tables[0].body_rows[4].cells[0].raw_text() == '5'
    assert doc.pages[0].tables[0].body_rows[4].cells[2].raw_text() == '80'
    assert doc.pages[0].tables[0].body_rows[4].cells[3].raw_text() == '5.2 AU'
