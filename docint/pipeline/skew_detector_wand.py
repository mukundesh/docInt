import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from ..vision import Vision


@Vision.factory(
    "skew_detector_wand",
    depends=["apt:libmagickwand-dev", "wand"],
    default_config={
        "conf_stub": "skew_detector_wand",
        "wand_library": True,
        "shave_percent": 0.0,
    },
)
class SkewDetectorWand:
    def __init__(self, conf_stub, wand_library, shave_percent):
        self.conf_stub = conf_stub
        self.wand_library = wand_library
        self.output_dir = Path("output")
        self.shave_percent = shave_percent

    def get_skew_cmdline_angle(self, page, orientation):
        bColor = "white"
        thresh = "80%"

        image_path = page.page_image.get_image_path()
        print(image_path)

        if orientation == "h":
            # compute horizontal angle
            cmdList = [
                "convert",
                image_path,
                "-shave",
                f"{self.shave_percent}%",
                "-background",
                bColor,
                "-deskew",
                thresh,
                "-print",
                "%[deskew:angle]",
                "null:",
            ]
            print(" ".join(str(c) for c in cmdList))
            horzAngle = subprocess.check_output(cmdList)
            return float(horzAngle)
        else:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_file_path = Path(temp_dir) / "tmp.png"

                subprocess.check_call(["convert", image_path, "-rotate", "90", temp_file_path])

                cmdList = [
                    "convert",
                    temp_file_path,
                    "-shave",
                    f"{self.shave_percent}%",
                    "-background",
                    bColor,
                    "-deskew",
                    thresh,
                    "-print",
                    "%[deskew:angle]",
                    "null:",
                ]
                vertAngle = subprocess.check_output(cmdList)
            return float(vertAngle)

    def get_skew_angle(self, page, orientation):
        from wand.image import Image

        print(page.page_image.get_image_path())

        with Image(
            filename=page.page_image.get_image_path()
        ) as image, tempfile.TemporaryDirectory() as tempdir:  # noqa
            # os.environ['MAGICK_TMPDIR'] = tempdir
            if orientation == "h":
                hor_image = image
                hor_image.deskew(0.8 * hor_image.quantum_range)
                angle = float(hor_image.artifacts["deskew:angle"])
            else:
                ver_image = image
                ver_image.rotate(90)
                ver_image.deskew(0.8 * ver_image.quantum_range)
                angle = float(ver_image.artifacts["deskew:angle"])
            image.destroy()
        return angle

    def __call__(self, doc):
        print(f"skew_detector_num_marker: {doc.pdf_name}")

        doc.add_extra_page_field("horz_skew_angle", ("noparse", "", ""))
        doc.add_extra_page_field("horz_skew_method", ("noparse", "", ""))

        json_path = self.output_dir / f"{doc.pdf_name}.skew_wand.json"
        if json_path.exists():
            jd = json.loads(json_path.read_text())
            skew_infos = jd["skew_infos"]
            assert len(doc.pages) == len(skew_infos)
            for (page, skew_info) in zip(doc.pages, skew_infos):
                page.horz_skew_angle = skew_info["horz_skew_angle"]
                page.horz_skew_method = skew_info["horz_skew_method"]

                page.vert_skew_angle = skew_info["vert_skew_angle"]
                page.vert_skew_method = skew_info["vert_skew_method"]
            return doc

        skew_infos = []
        for page in doc.pages:
            if self.wand_library:
                page.horz_skew_angle = self.get_skew_angle(page, "h")
            else:
                page.horz_skew_angle = self.get_skew_cmdline_angle(page, "h")

            page.horz_skew_method = "wand"

            if self.wand_library:
                page.vert_skew_angle = self.get_skew_angle(page, "v")
            else:
                page.vert_skew_angle = self.get_skew_cmdline_angle(page, "v")
            page.vert_skew_method = "wand"

            skew_infos.append(
                {
                    "horz_skew_angle": page.horz_skew_angle,
                    "horz_skew_method": page.horz_skew_method,
                    "vert_skew_angle": page.vert_skew_angle,
                    "vert_skew_method": page.vert_skew_method,
                }
            )
            print(f"> Page {page.page_idx} marker_angle={page.horz_skew_angle:.4f}")

        json_path.write_text(json.dumps({"skew_infos": skew_infos}))
        return doc
