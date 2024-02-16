import subprocess
from collections import Counter
from pathlib import Path

from ..shape import Coord
from ..vision import Vision

# TODO: 1. make image rotation optional -- why ???
# TODO: 2. no need to provide image dir as that should be picked up separately
# TODO: 3. logging


@Vision.factory(
    "page_rotator",
    depends=["apt:libmagickwand-dev", "wand"],
    default_config={"skew_method": "wand", "skew_cutoff": 0.25},
)
class RotatePage:
    def __init__(self, skew_method, skew_cutoff):
        self.skew_method = skew_method
        self.skew_cutoff = skew_cutoff

    def wand_rotate_image(self, image_path, angle):
        angle_str = f"-s{angle:.5}".replace(".", "_")
        new_image_path = image_path.parent / (image_path.stem + angle_str + image_path.suffix)
        print(new_image_path)

        from wand.image import Image as WandImage

        with WandImage(filename=str(image_path)) as image:
            image.rotate(angle)
            image.save(filename=str(new_image_path))
            new_size = (image.width, image.height)
        return new_image_path, new_size

    def wand_cmdline_rotate_image(self, image_path, angle):
        angle_str = f"-s{angle:.5}".replace(".", "_")
        new_image_path = image_path.parent / (image_path.stem + angle_str + image_path.suffix)
        print(new_image_path)

        subprocess.check_call(
            ["convert", image_path, "-rotate", str(angle), "+repage", new_image_path]
        )

        from PIL import Image as PILImage

        new_size = PILImage.open(new_image_path).size
        return new_image_path, new_size

    def pil_rotate_image(self, image_path, angle):
        angle_str = f"-s{angle:.5}".replace(".", "_")
        new_image_path = image_path.parent / (image_path.stem + angle_str + image_path.suffix)
        print(new_image_path)

        from PIL import Image as PILImage

        image = PILImage.open(image_path)
        image = image.rotate(-1 * angle, expand=True, fillcolor="white")
        image.save(new_image_path)
        return new_image_path, image.size

    def __call__(self, doc):
        print(f"Processing {doc.pdf_name}")
        doc.add_extra_page_field("rotated_angle", ("noparse", "", ""))
        for page in doc.pages:
            method = getattr(page, "horz_skew_method", "")
            if method != "wand":
                print(f"page_idx: {page.page_idx} method: {self.skew_method} not found.")
                continue

            angle = getattr(page, "horz_skew_angle", 0.0)
            if abs(angle) < self.skew_cutoff:
                print(f"page_idx: {page.page_idx} angle: {angle} < {self.skew_cutoff}.")
                continue

            print(f"page_idx: {page.page_idx} Rotating Angle: {angle}")
            page_image_path = Path(page.page_image.get_image_path())

            new_image_path, new_size = self.wand_cmdline_rotate_image(page_image_path, angle)

            page.page_image.update_image_path(new_image_path, new_size)

        return doc
