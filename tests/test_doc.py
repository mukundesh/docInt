from pathlib import Path

import pytest

from docint.doc import Doc
from docint.region import Region

small_json = '{"pdffile_path": "one_word.pdf", "pages": [{"page_idx": 0, "words": [{"page_idx": 0, "word_idx": 0, "text_": "One", "break_type": 1, "shape_": {"top": {"x": 0.1211429781512605, "y": 0.08872684085510685}, "bot": {"x": 0.15513645714285715, "y": 0.10297862232779094}}}], "width_": 595, "height_": 842}], "page_infos": [{"width": 595.0, "height": 842.0, "num_images": 0}], "page_images": [{"image_width": 2480.0, "image_height": 3509.0, "image_path": "orig-001-000.png", "image_box": {"top": {"x": 0.0, "y": 0.0}, "bot": {"x": 595.0, "y": 842.0}}, "image_type": "raster"}]}'


def test_properties(one_word_doc):
    doc = one_word_doc
    assert doc.num_pages == 1
    assert doc.pdf_name == "one_word.pdf"
    assert doc.pdf_stem == "one_word"
    assert doc.has_images == False  # noqa: E712


def test_words(one_word_doc):
    doc = one_word_doc
    assert doc.pages[0].words[0].text == "One"
    assert doc[0][0].text == "One"


@pytest.mark.skip(reason="pdf_path makes it hard to match, use file instead.")
def test_json(one_word_doc, tmp_path):
    assert one_word_doc.pdf_path == Path("one_word.pdf")
    tmp_file = tmp_path / "one_word.json"
    one_word_doc.to_disk(tmp_file)
    assert tmp_file.read_text() == small_json


def test_extra_obj(one_word_doc, tmp_path):
    one_word_doc.add_extra_field("marker", ("obj", "docint.region", "Region"))
    one_word_doc.add_extra_field("markers", ("list", "docint.region", "Region"))
    one_word_doc.add_extra_field("marker_dict", ("dict", "docint.region", "Region"))
    one_word_doc.add_extra_field("angle", ("noparse", "", ""))

    one_word = one_word_doc[0][0]
    one_region = Region.build(words=[one_word], page_idx=0)

    one_word_doc.marker = one_region
    one_word_doc.markers = [one_region]
    one_word_doc.marker_dict = {"first": one_region}

    # one_word_doc.angle = 0.75
    one_word_doc.angle = 1.5

    tmp_file = tmp_path / "one_word.json"
    one_word_doc.to_disk(tmp_file)

    read_doc = Doc.from_disk(tmp_file)
    assert id(read_doc[0][0]) == id(read_doc.markers[0].words[0])
    assert id(read_doc[0][0]) == id(read_doc.marker.words[0])
    assert id(read_doc[0][0]) == id(read_doc.marker_dict["first"].words[0])

    assert 1.5 == one_word_doc.angle


def test_page_info(one_word_doc):
    doc = one_word_doc
    assert doc.page_infos[0].width == 595.0
    assert doc.page_infos[0].height == 842.0
    assert doc.page_infos[0].num_images == 0


def test_page_image(one_word_doc):
    doc = one_word_doc
    doc.page_images[0].image_width = 2480.0
    doc.page_images[0].image_height = 3059.0
    doc.page_images[0].image_path = "orig-001-000.png"
    doc.page_images[0].image_type = "raster"
    doc.page_images[0].image_box.top.x = 0.0
    doc.page_images[0].image_box.bot.y = 842.0
