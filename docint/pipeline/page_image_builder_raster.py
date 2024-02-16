import json
from pathlib import Path
from typing import List

from pydantic import parse_obj_as
from pydantic.json import pydantic_encoder

from .. import pdfwrapper
from ..page_image import PageImage
from ..shape import Box, Coord
from ..util import get_full_path, get_repo_dir, is_repo_path
from ..vision import Vision


def build_raster_page_image(page, pdf_page, image_dir, image_format):
    page_num = page.page_idx + 1

    ext = "tif" if image_format == "tiff" else "png"

    image_stub = Path(page.doc.pdf_stem) / f"raster-{page_num:03d}-000.{ext}"
    if is_repo_path(image_dir):
        image_path = get_full_path(image_dir) / image_stub
    else:
        image_path = image_dir / image_stub

    image_repo_path = Path(image_dir) / image_stub
    # write the image to the file
    image_width, image_height = pdf_page.page_image_save(image_path)
    image_box = Box(top=Coord(x=0.0, y=0.0), bot=Coord(x=page.width, y=page.height))

    return PageImage(
        image_width=image_width,
        image_height=image_height,
        image_path=str(image_repo_path),
        image_box=image_box,
        image_type="raster",
        page_width=page.width,
        page_height=page.height,
        page_idx=page.page_idx,
    )


@Vision.factory(
    "page_image_builder_raster",
    default_config={
        "image_dir": ".img",
        "use_cache": True,
        "image_format": "png",
    },
)
class PageImageBuilderRaster:
    def __init__(self, image_dir, use_cache, image_format):
        self.image_dir = image_dir
        self.use_cache = use_cache
        self.repo_dir = get_repo_dir()

        self.image_format = image_format
        assert self.image_format in ("png", "tiff")

        assert is_repo_path(self.image_dir) or Path(self.image_dir).exists()

    def __call__(self, doc, pipe_config={}):
        doc.add_extra_page_field("page_image", ("obj", "docint.page_image", "PageImage"))

        if is_repo_path(self.image_dir):
            image_dir_path = get_full_path(self.image_dir, self.repo_dir)
        else:
            image_dir_path = Path(self.image_dir)

        doc_image_dir = image_dir_path / doc.pdf_stem
        json_path = doc_image_dir / f"{doc.pdf_name}.page_image.json"
        print(f"Use Cache, {self.use_cache}")

        if self.use_cache and json_path.exists():
            page_image_dict = json.loads(json_path.read_text())
            page_images = parse_obj_as(List[PageImage], page_image_dict["page_images"])
            assert len(page_images) == len(doc.pages)
            for page, page_image in zip(doc.pages, page_images):
                page.page_image = page_image
            return doc

        if not doc_image_dir.exists():
            doc_image_dir.mkdir(exist_ok=True, parents=True)

        pdf = pdfwrapper.open(doc.pdf_path, library_name="pypdfium2")

        page_images = []
        for page, pdf_page in zip(doc.pages, pdf.pages):
            page_image = build_raster_page_image(page, pdf_page, self.image_dir, self.image_format)
            page.page_image = page_image
            page_images.append(page_image)

        if self.use_cache:
            page_images_info = {"page_images": page_images}
            json_str = json.dumps(page_images_info, default=pydantic_encoder, indent=2)
            json_path.write_text(json_str)
        return doc
