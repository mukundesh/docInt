import logging
import math
import sys
from pathlib import Path
from statistics import mean

import numpy as np

from ..shape import Poly
from ..vision import Vision


@Vision.factory(
    "rotation_detector",
    default_config={
        "min_text_len": 4,
        "min_num_markers": 3,
        "conf_stub": "rotation_detector",
    },
)
class RotationDetector:
    def __init__(self, min_text_len, min_num_markers, conf_stub):
        self.min_text_len = min_text_len
        self.min_num_markers = min_num_markers
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

    def get_num_markers_angle(self, page):
        num_markers = getattr(page, "num_markers", [])
        if len(num_markers) < self.min_num_markers:
            return -0.0

        marker_words = [m.words[0] for m in num_markers]
        m_xmids = [w.xmid for w in marker_words]
        m_ymids = [w.ymid for w in marker_words]

        m_xdiffs = [m_xmids[idx] - m_xmids[0] for idx in range(len(num_markers))]
        m_ydiffs = [m_ymids[idx] - m_ymids[0] for idx in range(len(num_markers))]

        y = [mx * page.width for mx in m_xdiffs]
        x = [my * page.height for my in m_ydiffs]

        A = np.vstack([x, np.ones(len(x))]).T
        pinv = np.linalg.pinv(A)
        alpha = pinv.dot(y)
        angle = math.degrees(math.atan(alpha[0]))
        return angle

    def get_word_box_angle(self, page):
        def line_angle(c1, c2):
            [lft, rht] = sorted([c1, c2], key=lambda c: c.x)
            if c2.x != c1.x:
                alpha = (c2.y - c1.y) / (c2.x - c1.x)
                return math.degrees(math.atan(alpha))
            else:
                print("Error")
                return 0.0

        angles = []
        for word in page.words:
            if isinstance(word.shape, Poly) and len(word) >= self.min_text_len:
                coords = word.shape.coords
                top_angle = line_angle(coords[0], coords[1])
                bot_angle = line_angle(coords[2], coords[3])
                angles.append(mean((top_angle, bot_angle)))
        return mean(angles)

    def get_skew_angle(self, page, orientation="h"):
        return page.page_image.get_skew_angle(orientation)

    def __call__(self, doc):
        print(f"Detect Rotation {doc.pdf_name}")

        doc.add_extra_page_field("num_marker_angle", ("noparse", "", ""))
        doc.add_extra_page_field("horz_skew_angle", ("noparse", "", ""))
        doc.add_extra_page_field("vert_skew_angle", ("noparse", "", ""))
        doc.add_extra_page_field("word_box_angle", ("noparse", "", ""))

        for page in doc.pages:
            page.num_marker_angle = self.get_num_markers_angle(page)
            # page.horz_skew_angle = self.get_skew_angle(page, orientation="h")
            # page.vert_skew_angle = self.get_skew_angle(page, orientation="v")
            # page.word_box_angle = self.get_word_box_angle(page)

            # print(f'> Page {page.page_idx} marker_angle={page.num_marker_angle:.4f} horz_skew={page.horz_skew_angle:.4f} vert_skew={page.vert_skew_angle:.4f} word_box={page.word_box_angle:.4f}')
            print(f"> Page {page.page_idx} marker_angle={page.num_marker_angle:.4f}")
            # page.word_box_angle = self.get_word_box_angle(page)
        return doc
