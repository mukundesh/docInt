import json
import subprocess
from pathlib import Path
from typing import List

from PIL import Image
from pydantic import parse_obj_as
from pydantic.json import pydantic_encoder

from .. import pdfwrapper
from ..page_image import PageImage
from ..shape import Box
from ..util import get_full_path, get_repo_dir, is_repo_path
from ..vision import Vision
from .page_image_builder_raster import build_raster_page_image

# TODO: if the page is rotated the image should also be rotated, I think image_box
#       should also be adjusted.
#       I.P.S.Transfer02082013_171139.pdf page_num=2 is rotated by 180.
#


def is_small_size(image_path, minimum_size):
    if is_repo_path(image_path):
        image_path = get_full_path(str(image_path))
    img = Image.open(image_path)
    if img.width < minimum_size or img.height < minimum_size:
        return True
    else:
        return False


def extract_images(pdf_path, image_root, page_num, format="png"):
    assert format in ("png", "tiff")
    cmd = [
        "pdfimages",
        "-f",
        str(page_num),
        "-l",
        str(page_num),
        "-p",
        f"-{format}",
        str(pdf_path),
        str(image_root),
    ]
    print(cmd)
    subprocess.check_call(cmd)


def build_embedded_page_image(
    page, pdf_page, image_dir_repo, image_dir_path, minimum_size, image_format
):
    page_num = page.page_idx + 1

    ext = "tif" if image_format == "tiff" else "png"

    image_root = image_dir_path / Path(page.doc.pdf_stem) / "embedded"
    image_path = image_dir_repo / Path(page.doc.pdf_stem) / f"embedded-{page_num:03d}-000.{ext}"
    image_width, image_height = pdf_page.images[0].size
    image_box = Box.from_bounding_box(pdf_page.images[0].bounding_box)

    extract_images(page.doc.pdf_path, image_root, page_num, image_format)
    if is_small_size(image_path, minimum_size):
        return build_raster_page_image(page, pdf_page, image_dir_repo, image_format)
    else:
        return PageImage(
            image_width=image_width,
            image_height=image_height,
            image_path=str(image_path),
            image_box=image_box,
            image_type="embedded",
            page_width=pdf_page.width,
            page_height=pdf_page.height,
            page_idx=page.page_idx,
        )


@Vision.factory(
    "page_image_builder_embedded",
    depends=["apt:poppler-utils"],
    default_config={
        "image_dir": ".img",
        "use_cache": True,
        "minimum_size": 500,
        "image_format": "png",
    },
)
class PageImageBuilderEmbedded:
    def __init__(self, image_dir, use_cache, minimum_size, image_format):
        self.image_dir = image_dir
        self.use_cache = use_cache
        self.repo_dir = get_repo_dir()
        self.minimum_size = minimum_size
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

        if self.use_cache and json_path.exists():
            print(f"JSON FOUND {str(json_path)}")
            page_image_dict = json.loads(json_path.read_text())
            page_images = parse_obj_as(List[PageImage], page_image_dict["page_images"])
            assert len(page_images) == len(doc.pages)
            for page, page_image in zip(doc.pages, page_images):
                page.page_image = page_image
            return doc
        else:
            print("JSON NOT FOUND")

        if not doc_image_dir.exists():
            doc_image_dir.mkdir(exist_ok=True, parents=True)

        pdf = pdfwrapper.open(doc.pdf_path, library_name="pypdfium2")

        page_images = []
        for (page, pdf_page) in zip(doc.pages, pdf.pages):
            if len(pdf_page.images) == 1:
                pdf_image = pdf_page.images[0]

                # pdfimages is not able to handle stencil images, which have 1 bit per pixel
                # it creates all black images that are hard for ML routines to handle
                # here we generate a raster image in that case, ideally we should extract the data
                # and build an image,
                # https://stackoverflow.com/a/34555343
                # note the commented code at bottom
                if (
                    pdf_image.colorspace_str == "FPDF_COLORSPACE_UNKNOWN"
                    and pdf_image.bits_per_pixel == 1
                    and "CCITTFaxDecode" in pdf_image.get_filters()
                ):
                    print("CCITTFaxDecode image, generating raster image")
                    page_image = build_raster_page_image(page, pdf_page, self.image_dir)
                else:
                    page_image = build_embedded_page_image(
                        page,
                        pdf_page,
                        self.image_dir,
                        image_dir_path,
                        self.minimum_size,
                        self.image_format,
                    )
            else:
                page_image = build_raster_page_image(
                    page, pdf_page, self.image_dir, self.image_format
                )

            page.page_image = page_image
            page_images.append(page_image)

        if self.use_cache:
            page_images_info = {"page_images": page_images}
            json_str = json.dumps(page_images_info, default=pydantic_encoder, indent=2)
            json_path.write_text(json_str)
        return doc
