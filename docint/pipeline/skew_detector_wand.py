import logging
import sys
from pathlib import Path

from ..vision import Vision


@Vision.factory(
    "skew_detector_wand",
    depends=["apt:libmagickwand-dev", "wand"],
    default_config={
        "conf_stub": "skew_detector_wand",
    },
)
class SkewDetectorWand:
    def __init__(self, conf_stub):
        self.conf_stub = conf_stub

        self.lgr = logging.getLogger(f"docint.pipeline.{self.conf_stub}")
        self.lgr.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)
        self.file_handler = None

    def add_log_handler(self, doc):
        handler_name = f"{doc.pdf_name}.{self.conf_stub}.log"
        log_path = Path("logs") / handler_name
        self.file_handler = logging.FileHandler(log_path, mode="w")
        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def get_skew_angle(self, page, orientation):
        from wand.image import Image

        with Image(filename=page.page_image.image_path) as image:
            if orientation == "h":
                hor_image = image
                hor_image.deskew(0.8 * hor_image.quantum_range)
                angle = float(hor_image.artifacts["deskew:angle"])
            else:
                ver_image = image
                ver_image.rotate(90)
                ver_image.deskew(0.8 * ver_image.quantum_range)
                angle = float(ver_image.artifacts["deskew:angle"])
        return angle

    def __call__(self, doc):
        print(f"skew_detector_num_marker: {doc.pdf_name}")

        doc.add_extra_page_field("horz_skew_angle", ("noparse", "", ""))
        doc.add_extra_page_field("horz_skew_method", ("noparse", "", ""))

        for page in doc.pages:
            page.horz_skew_angle = self.get_skew_angle(page, "h")
            page.horz_skew_method = "wand"

            page.vert_skew_angle = self.get_skew_angle(page, "v")
            page.vert_skew_method = "wand"

            # print(f"> Page {page.page_idx} marker_angle={page.horz_skew_angle:.4f}")

        return doc
