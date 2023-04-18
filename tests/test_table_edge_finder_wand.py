import pytest  # noqa

import docint

docker_config = {
    "post_install_lines": [
        "ENV GOOGLE_APPLICATION_CREDENTIALS /usr/src/app/task_/.secrets/google.token"
    ],
    "is_recognizer": True,
    "delete_container_dir": True,
}

# @pytest.mark.skip("skipping for now")


def test_pdftable_finder(table_path):
    ppln = docint.empty(
        config={"docker_pipes": ["table_edge_finder_wand"], "docker_config": docker_config}
    )
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_raster")
    ppln.add_pipe("num_marker")
    ppln.add_pipe(
        "table_edge_finder_wand", pipe_config={"expected_columns": 4, "skew_threshold": 0.0}
    )
    doc = ppln(table_path)

    # vert_edges = [e for e in doc.pages[0].table_edges_list if e.orientation == "v"]
    # horz_edges = [e for e in doc.pages[0].table_edges_list if e.orientation == "h"]

    vert_edges = doc.pages[0].table_edges_list[0].col_edges
    horz_edges = doc.pages[0].table_edges_list[0].row_edges

    vert_edges_image_x = [doc[0].get_image_coord(e.coord1).x for e in vert_edges]
    assert vert_edges_image_x == [145.0, 326.0, 506.0, 686.0, 867.0]

    horz_edges_image_x = [doc[0].get_image_coord(e.coord1).y for e in horz_edges]
    assert horz_edges_image_x == [
        349.0,
        380.0,
        410.0,
        441.0,
        471.0,
        501.0,
        531.0,
        561.0,
        592.0,
        625.0,
    ]


# TODO PLEASE ADD THIS
# @pytest.mark.skip("skipping for now")
def test_pdftable_rota_finder(table_rota_path):
    ppln = docint.empty(
        config={
            "docker_pipes": ["gcv_recognizer", "table_edge_finder_wand"],
            "docker_config": docker_config,
        }
    )
    ppln.add_pipe("gcv_recognizer", pipe_config={"bucket": "orgfound"})
    ppln.add_pipe("page_image_builder_raster")
    ppln.add_pipe("num_marker")
    ppln.add_pipe(
        "table_edge_finder_wand", pipe_config={"expected_columns": 4, "skew_threshold": 1.0}
    )
    ppln.add_pipe("table_builder_on_edges")
    ppln.add_pipe(
        "html_generator",
        pipe_config={
            "html_root": "output/html",
            "color_dict": {"word": "blue", "table_edges": "green"},
        },
    )

    doc = ppln(table_rota_path)

    # vert_edges = [e for e in doc.pages[0].edges if e.orientation == "v"]
    # horz_edges = [e for e in doc.pages[0].edges if e.orientation == "h"]

    vert_edges = doc.pages[0].table_edges_list[0].col_edges
    horz_edges = doc.pages[0].table_edges_list[0].row_edges

    vert_edges_image_x = [doc[0].get_image_coord(e.coord1).x for e in vert_edges]
    # Table extraction is wrong but till then..
    assert vert_edges_image_x == [217.0, 402.0, 587.0, 772.0, 957.0]

    horz_edges_image_y = [doc[0].get_image_coord(e.coord1).y for e in horz_edges]
    print(horz_edges_image_y)
    assert horz_edges_image_y == [
        386.0,
        418.0,
        447.0,
        481.0,
        510.0,
        542.0,
        572.0,
        603.0,
        635.0,
        669.0,
    ]
