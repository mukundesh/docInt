import math

import docint

docker_config = {
    "post_install_lines": ["ENV GOOGLE_APPLICATION_CREDENTIALS /usr/src/app/task_/.secrets/google.token"],
    "delete_container_dir": True,
}


def test_skew_finder(table_path):
    # ppln = docint.empty(config={"docker_pipes": ["skew_detector_wand"], "docker_config": docker_config})
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("skew_detector_wand")
    doc = ppln(table_path)
    assert abs(doc[0].horz_skew_angle) < 0.05
    assert doc[0].horz_skew_method == "wand"


def test_rota_skew_finder(table_rota_path):
    ppln = docint.empty(config={"docker_pipes": ["skew_detector_wand"], "docker_config": docker_config})
    ppln.add_pipe("pdf_reader")  # doesn't matter as we only need page_image
    ppln.add_pipe("skew_detector_wand")
    doc = ppln(table_rota_path)

    assert math.isclose(doc[0].horz_skew_angle, -3.1, rel_tol=1e-1)
    assert math.isclose(doc[0].vert_skew_angle, -3.1, rel_tol=1e-1)
    assert doc[0].horz_skew_method == "wand"


# def test_rota_skew_finder_max_num_marker(table_rota_path):
#     ppln = docint.empty(config={"docker_pipes": ["gcv_recognizer", "skew_detector_num_marker"], "docker_config": docker_config})
#     ppln.add_pipe("gcv_recognizer", pipe_config={'bucket': 'orgfound'})
#     ppln.add_pipe("num_marker", pipe_config={'min_marker': 10})
#     ppln.add_pipe("skew_detector_num_marker")
#     doc = ppln(table_rota_path)

#     assert doc[0].horz_skew_angle is None
#     assert doc[0].horz_skew_method == "num_marker"
