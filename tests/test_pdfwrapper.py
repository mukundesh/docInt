from math import isclose

import pytest

from docint import pdfwrapper

REL_TOL = 1e-2


def float_eq(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(isclose(a1, b1, rel_tol=REL_TOL) for (a1, b1) in zip(a, b))
    else:
        print(a, b)
        return isclose(a, b, rel_tol=REL_TOL)


@pytest.mark.parametrize("library_name", ["pypdfium2"])
def test_page(images_path, library_name):

    pdf = pdfwrapper.open(images_path, library_name=library_name)
    assert len(pdf.pages) == 1

    assert pdf.pages[0].width == 595
    assert pdf.pages[0].height == 842
    assert len(pdf.pages[0].words) == 12
    assert len(pdf.pages[0].images) == 2


@pytest.mark.parametrize("library_name", ["pypdfium2"])
def test_image(images_path, library_name):
    pdf = pdfwrapper.open(images_path, library_name=library_name)

    image = pdf.pages[0].images[0]

    assert image.width == 640
    assert image.height == 546
    assert float_eq(image.bounding_box, [73.0, 72.0, 438.4943, 383.8])

    assert image.to_pil().size == (640, 546)


@pytest.mark.parametrize("library_name", ["pypdfium2"])
def test_word(images_path, library_name):
    pdf = pdfwrapper.open(images_path, library_name=library_name)
    word = pdf.pages[0].words[7]
    assert word.text == "by"
    assert float_eq(word.bounding_box, [103.97247200000001, 734.228, 115.71327200000002, 746.228])
