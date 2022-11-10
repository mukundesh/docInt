import math

import docint
from docint.page_image import ImageContext
from docint.shape import Coord


def test_dimensions(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_raster", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    assert doc[0].page_image.image_width == 668
    assert doc[0].page_image.image_height == 945

    assert doc[0].page_image.image_box.top.x == 0.0
    assert doc[0].page_image.image_box.bot.x == 595.0

    assert doc[0].page_image.image_box.top.y == 0.0
    assert doc[0].page_image.image_box.bot.y == 842.0

    assert doc[0].page_image.size == (668, 945)


def test_coords(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_raster", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    mid_point = Coord(x=0.5, y=0.5)

    image_mid_point = doc[0].page_image.get_image_coord(mid_point)
    assert image_mid_point.x == 334
    assert image_mid_point.y == 472

    doc_mid_point = doc[0].page_image.get_doc_coord(image_mid_point)

    assert math.isclose(doc_mid_point.x, 0.5, rel_tol=1e-2)
    assert math.isclose(doc_mid_point.y, 0.5, rel_tol=1e-2)


def test_crop(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_raster", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    with ImageContext(doc[0].page_image) as image:
        image.crop(top=Coord(x=0.2, y=0.3), bot=Coord(x=0.8, y=0.7))

        # (0.8 - 0.2) * 668
        assert image.width == 400

        # (0.7 - 0.3) * 945
        assert image.height == 378

        crop_top_img_coord = image.get_image_coord(Coord(x=0.2, y=0.3))
        assert crop_top_img_coord.x == 0.0
        assert crop_top_img_coord.y == 0.0

        crop_top_doc_coord = image.get_doc_coord(crop_top_img_coord)
        assert math.isclose(crop_top_doc_coord.x, 0.2006, rel_tol=1e-3)
        assert math.isclose(crop_top_doc_coord.y, 0.3005, rel_tol=1e-3)

        mid_img_coord = image.get_image_coord(Coord(x=0.5, y=0.5))
        # (0.5 - 0.2)/(0.8 - 0.2) * 400
        assert mid_img_coord.x == 200

        # (0.5 - 0.3)/(0.7 - 0.3) * 377
        assert mid_img_coord.y == 188

        mid_doc_coord = image.get_doc_coord(mid_img_coord)
        print(mid_doc_coord)
        assert math.isclose(mid_doc_coord.x, 0.5, rel_tol=1e-3)
        assert math.isclose(mid_doc_coord.y, 0.4995, rel_tol=1e-3)


def test_rotate(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_raster", pipe_config={"use_cache": False})
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
        assert img_coord.x == 165
        assert img_coord.y == 279
        # CHECKED


def test_crop_rotate(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_raster", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    print("Before", doc[0].page_image.get_image_coord(Coord(x=0.2, y=0.2)))

    with ImageContext(doc[0].page_image) as image:
        image.crop(Coord(x=0.1, y=0.1), Coord(x=0.9, y=0.9))
        assert image.size == (534, 756)

        image.rotate(10)
        assert image.size == (658, 838)

        img_mid_coord = image.get_image_coord(Coord(x=0.5, y=0.5))
        assert img_mid_coord.x == 329
        assert img_mid_coord.y == 419

        # NOT CHECKED TODO
        img_coord = image.get_image_coord(Coord(x=0.2, y=0.2))
        assert img_coord.x == 83
        assert img_coord.y == 175


def test_rotate_crop(page_image_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("page_image_builder_raster", pipe_config={"use_cache": False})
    doc = ppln(page_image_path)

    print("Before", doc[0].page_image.get_image_coord(Coord(x=0.2, y=0.2)))

    with ImageContext(doc[0].page_image) as image:
        image.rotate(10)
        assert image.size == (822, 1047)

        image.crop(Coord(x=0.1, y=0.1), Coord(x=0.9, y=0.9))
        assert image.size == (657, 652)

        img_mid_coord = image.get_image_coord(Coord(x=0.5, y=0.5))
        print(img_mid_coord)

        assert img_mid_coord.x == 329
        assert img_mid_coord.y == 326

        # NOT CHECKED TODO
        img_coord = image.get_image_coord(Coord(x=0.2, y=0.2))
        print(img_coord)
        assert img_coord.x == 83
        assert img_coord.y == 82
