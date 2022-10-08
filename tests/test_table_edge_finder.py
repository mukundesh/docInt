import docint


def test_pdftable_finder(table_path):
    ppln = docint.empty()
    ppln.add_pipe('pdf_reader')
    ppln.add_pipe('num_marker')
    ppln.add_pipe('table_edge_finder', pipe_config={'expected_columns': 4})
    doc = ppln(table_path)

    vert_edges = [e for e in doc.pages[0].edges if e.orientation == 'v']
    horz_edges = [e for e in doc.pages[0].edges if e.orientation == 'h']

    vert_edges_image_x = [doc[0].get_image_coord(e.coord1).x for e in vert_edges]
    assert vert_edges_image_x == [300.0, 679.0, 1055.0, 1430.0, 1805.0]

    horz_edges_image_x = [doc[0].get_image_coord(e.coord1).y for e in horz_edges]
    assert horz_edges_image_x == [725.0, 788.0, 850.0, 913.0, 975.0, 1038.0, 1104.0, 1167.0, 1229.0, 1296.0]
