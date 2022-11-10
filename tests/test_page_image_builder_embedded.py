import math

import docint
from docint.page_image import ImageContext
from docint.shape import Coord


def test_dimensions(page_image_path):
    # ppln = docint.empty(config={"docker_pipes": ["page_image_builder_embedded"]})
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_embedded", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    assert doc[0].page_image.image_width == 506
    assert doc[0].page_image.image_height == 706

    assert math.isclose(doc[0].page_image.image_box.top.x, 73, rel_tol=1.0e-3)
    assert math.isclose(doc[0].page_image.image_box.top.y, 72, rel_tol=1.0e-3)

    assert math.isclose(doc[0].page_image.image_box.bot.x, 524.30, rel_tol=1.0e-3)
    assert math.isclose(doc[0].page_image.image_box.bot.y, 701.70, rel_tol=1.0e-3)

    assert doc[0].page_image.size == (506, 706)


def test_coords(page_image_path):
    # TODO cannot run this in docker as PDF file is not getting passed to container
    # ppln = docint.empty(config={"docker_pipes": ["page_image_builder_embedded"]})
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_embedded", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    doc_mid_point = Coord(x=0.5, y=0.5)
    img_doc_mid_point = doc[0].page_image.get_image_coord(doc_mid_point)

    assert img_doc_mid_point.x == 252
    assert img_doc_mid_point.y == 391

    img_mid_point = Coord(x=253, y=353)
    doc_img_mid_point = doc[0].page_image.get_doc_coord(img_mid_point)

    # (((524.30-73)/506 * 253) + 73)/595
    assert math.isclose(doc_img_mid_point.x, 0.5019, rel_tol=1e-3)

    # (((701.70-72)/706 * 353) + 72)/842
    assert math.isclose(doc_img_mid_point.y, 0.4594, rel_tol=1e-3)

    img_top_point = Coord(x=0, y=0)
    doc_img_top_point = doc[0].page_image.get_doc_coord(img_top_point)

    # 0.1226890756302521
    assert math.isclose(doc_img_top_point.x, 0.1227, rel_tol=1e-3)
    assert math.isclose(doc_img_top_point.y, 0.0855, rel_tol=1e-3)


def test_crop(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_embedded", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    with ImageContext(doc[0].page_image) as image:
        image.crop(top=Coord(x=0.2, y=0.3), bot=Coord(x=0.8, y=0.7))
        print(image.size)

        # (0.8 - 0.2) * 668
        assert image.width == 400

        # (0.7 - 0.3) * 945
        assert image.height == 377

        crop_top_img_coord = image.get_image_coord(Coord(x=0.2, y=0.3))
        assert crop_top_img_coord.x == 0.0
        assert crop_top_img_coord.y == 0.0

        mid_img_coord = image.get_image_coord(Coord(x=0.5, y=0.5))
        # (0.5 - 0.2)/(0.8 - 0.2) * 400
        assert mid_img_coord.x == 200

        # (0.5 - 0.3)/(0.7 - 0.3) * 377
        assert mid_img_coord.y == 188


def test_rotate(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_embedded", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    print("Before", doc[0].page_image.get_image_coord(Coord(x=0.2, y=0.2)))

    with ImageContext(doc[0].page_image) as image:
        # TODO this needs be changed to +10
        image.rotate(10)
        # (824, 1049)
        print(image.size)

        img_mid_coord = image.get_image_coord(Coord(x=0.5, y=0.5))
        img_mid_coord.x == 413
        img_mid_coord.y == 525

        img_coord = image.get_image_coord(Coord(x=0.2, y=0.2))

        # NOT CHECKED TODO
        assert img_coord.x == 71
        assert img_coord.y == 186


def test_crop_rotate(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_embedded", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    print("Before", doc[0].page_image.get_image_coord(Coord(x=0.2, y=0.2)))

    with ImageContext(doc[0].page_image) as image:
        image.crop(Coord(x=0.1, y=0.1), Coord(x=0.9, y=0.9))
        assert image.size == (506, 693)

        image.rotate(10)
        assert image.size == (620, 771)

        img_mid_coord = image.get_image_coord(Coord(x=0.5, y=0.5))

        assert img_mid_coord.x == 314
        assert img_mid_coord.y == 417

        # NOT CHECKED TODO
        img_coord = image.get_image_coord(Coord(x=0.2, y=0.2))

        assert img_coord.x == 68
        assert img_coord.y == 173


def test_rotate_crop(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_embedded", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    print("Before", doc[0].page_image.get_image_coord(Coord(x=0.2, y=0.2)))

    with ImageContext(doc[0].page_image) as image:
        image.rotate(10)
        assert image.size == (622, 784)

        image.crop(Coord(x=0.1, y=0.1), Coord(x=0.9, y=0.9))
        assert image.size == (618, 595)

        img_mid_coord = image.get_image_coord(Coord(x=0.5, y=0.5))
        assert img_mid_coord.x == 314
        assert img_mid_coord.y == 329

        # NOT CHECKED TODO
        img_coord = image.get_image_coord(Coord(x=0.2, y=0.2))
        assert img_coord.x == 68
        assert img_coord.y == 85


def test_noimage(unicode_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_embedded", pipe_config={"use_cache": False})
    doc = ppln(unicode_path)  # noqa

    # NOT CHECKED TODO
