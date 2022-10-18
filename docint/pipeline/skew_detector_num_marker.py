import logging
import math
import sys
from collections import Counter
from pathlib import Path

from ..vision import Vision


@Vision.factory(
    "skew_detector_num_marker",
    depends=["numpy"],
    default_config={
        "min_marker": 3,
        "conf_stub": "skew_detector_num_marker",
    },
)
class SkewDetectorNumMarker:
    def __init__(self, min_marker, conf_stub):
        self.min_marker = min_marker
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
        if len(num_markers) < self.min_marker:
            return None

        # Find which type of num markers are more
        num_type_counter = Counter(m.num_type for m in num_markers)
        max_type = max(num_type_counter, key=num_type_counter.get)

        marker_words = [m.words[0] for m in num_markers if m.num_type == max_type and m.num_val != 0]

        m_xmids = [w.xmid for w in marker_words]
        m_ymids = [w.ymid for w in marker_words]

        m_xdiffs = [m_xmids[idx] - m_xmids[0] for idx in range(len(marker_words))]
        m_ydiffs = [m_ymids[idx] - m_ymids[0] for idx in range(len(marker_words))]

        y = [mx * page.width for mx in m_xdiffs]
        x = [my * page.height for my in m_ydiffs]

        import numpy as np

        A = np.vstack([x, np.ones(len(x))]).T
        pinv = np.linalg.pinv(A)
        alpha = pinv.dot(y)
        angle = math.degrees(math.atan(alpha[0]))
        return angle

    def __call__(self, doc):
        print(f"skew_detector_num_marker: {doc.pdf_name}")

        doc.add_extra_page_field("horz_skew_angle", ("noparse", "", ""))
        doc.add_extra_page_field("horz_skew_method", ("noparse", "", ""))

        for page in doc.pages:
            page.horz_skew_angle = self.get_num_markers_angle(page)
            page.horz_skew_method = "num_marker"
            # print(f"> Page {page.page_idx} marker_angle={page.horz_skew_angle:.4f}")

        return doc
