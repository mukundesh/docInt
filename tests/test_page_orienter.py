from pathlib import Path

import pytest

import docint


@pytest.mark.parametrize(
    "pdf_path, orient_angle",
    [
        ('3lines-0rotated.pdf', 0),
        ('3lines-90rotated.pdf', 90),
        ('3lines-180rotated.pdf', 180),
        ('3lines-270rotated.pdf', 270),
    ],
)
def test_orient_angle(pdf_path, orient_angle):
    ppln = docint.empty()
    ppln.add_pipe('gcv_recognizer', pipe_config={'bucket': 'orgp'})
    ppln.add_pipe('orient_pages', pipe_config={'images_dir': ''})
    doc = ppln(Path('tests') / pdf_path)
    assert doc[0].reoriented_angle == orient_angle
