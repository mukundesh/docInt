import docint

docker_config = {
    "delete_container_dir": True,
}


def test_pdftable_finder(table_path):
    ppln = docint.empty(config={"docker_pipes": ["table_edge_finder"], "docker_config": docker_config})
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("num_marker")
    ppln.add_pipe("table_edge_finder", pipe_config={"expected_columns": 4})
    doc = ppln(table_path)

    vert_edges = [e for e in doc.pages[0].edges if e.orientation == "v"]
    horz_edges = [e for e in doc.pages[0].edges if e.orientation == "h"]

    vert_edges_image_x = [doc[0].get_image_coord(e.coord1).x for e in vert_edges]
    print(vert_edges_image_x)
    assert vert_edges_image_x == [144.0, 326.0, 506.0, 686.0, 868.0]

    horz_edges_image_x = [doc[0].get_image_coord(e.coord1).y for e in horz_edges]
    assert horz_edges_image_x == [
        350.0,
        380.0,
        410.0,
        440.0,
        470.0,
        502.0,
        532.0,
        562.0,
        592.0,
        626.0,
    ]
