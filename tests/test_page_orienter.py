from pathlib import Path

import pytest

import docint

docker_config = {
    "post_install_lines": [
        "ENV GOOGLE_APPLICATION_CREDENTIALS /usr/src/app/task_/.secrets/google.token"
    ],
    "is_recognizer": True,
    "delete_container_dir": True,
}


@pytest.mark.parametrize(
    "pdf_path, orient_angle",
    [
        ("3lines-0rotated.pdf", 0),
        ("3lines-90rotated.pdf", 90),
        ("3lines-180rotated.pdf", 180),
        ("3lines-270rotated.pdf", 270),
    ],
)
def test_orient_angle(pdf_path, orient_angle):
    ppln = docint.empty(config={"docker_pipes": ["gcv_recognizer"], "docker_config": docker_config})
    ppln.add_pipe("gcv_recognizer", pipe_config={"bucket": "orgfound"})
    ppln.add_pipe("page_image_builder_raster")
    ppln.add_pipe("orient_pages")
    print("Inside test_orient_angle")
    doc = ppln(Path("tests") / pdf_path)
    assert doc[0].reoriented_angle == orient_angle
