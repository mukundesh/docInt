import logging
import statistics
import sys
from pathlib import Path

from ..page import Page
from ..util import load_config
from ..vision import Vision
from ..word_line import words_in_lines
from .list_finder import ListItem


def parse_range(astr):
    result = set()
    if isinstance(astr, list):
        return astr

    for part in astr.split(','):
        x = part.split('-')
        result.update(range(int(x[0]), int(x[-1]) + 1))
    return sorted(result)


@Vision.factory(
    "nonum_list_finder",
    default_config={
        "doc_confdir": "conf",
        "pre_edit": True,
        "page_idxs": [],
        "x_range": (0.0, 0.2),
        "y_range": (0.09, 1.0),
        "has_footer": True,
        "footer_delim": ".,;",
        "footer_height_multiple": 2.0,
        "rotation_config": {
            "rotation_strategy": "none",
            "rotation_arg": None,
            "rotation_page_idxs": [],
            "rotation_min_angle": 0.05,
        },
        "conf_stub": "listfinder",
    },
)
class NonumberListFinder:
    def __init__(
        self,
        doc_confdir,
        pre_edit,
        page_idxs,
        x_range,
        y_range,
        has_footer,
        footer_delim,
        footer_height_multiple,
        rotation_config,
        conf_stub,
    ):
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.page_idxs = parse_range(page_idxs)
        self.x_range = x_range
        self.y_range = y_range
        self.has_footer = has_footer
        self.footer_delim = footer_delim
        self.footer_height_multiple = footer_height_multiple
        self.rotation_config = rotation_config
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
        self.lgr.info(f"adding handler {log_path}")

        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def remove_footer(self, word_lines):
        def to_str(word_lines):
            return "\n".join([" ".join(w.text for w in line) for line in word_lines])

        self.lgr.debug("** Inside Footer processing")
        last_word_lines = []
        footer_delim_tuple = tuple(self.footer_delim)
        heights = [w.box.height for wl in word_lines for w in wl]
        avg_height = statistics.mean(heights) if heights else 0.0
        height_cutoff = avg_height * self.footer_height_multiple

        if not heights:
            return [[]]

        prev_ymin = -1.0
        for word_line in [wl for wl in word_lines if wl]:
            ymin = statistics.mean([w.box.ymin for w in word_line])
            if prev_ymin != -1.0 and (ymin - prev_ymin) > height_cutoff:
                self.lgr.debug(f"line break found {to_str(last_word_lines)} {ymin-prev_ymin} > {height_cutoff}")
                break
            prev_ymin = ymin

            line_text = " ".join(w.text for w in word_line if w.text)

            self.lgr.debug(f"footer adding: {line_text}")
            last_word_lines.append(word_line)

            if line_text.strip().endswith(footer_delim_tuple):
                self.lgr.debug(f"end of line {to_str(last_word_lines)}")
                break
        return last_word_lines

    def find_inpage(self, word_lines, num_markers, page_path):
        def build_list_item(marker, word_lines):
            word_lines[0] = [marker] + word_lines[0]
            return ListItem.build(None, word_lines)

        def to_str(word_lines):
            return "\n".join([" ".join(w.text for w in line) for line in word_lines])

        # assumption that word_lines and num_markers are similarly ordered.
        list_items = []
        if not num_markers:
            return list_items

        item_word_lines, m_idx, marker = [], 0, num_markers[0]

        self.lgr.debug(f"> Page {page_path} word_markers: {len(num_markers)}")
        for word_line in word_lines:
            item_word_line = []
            for word in word_line:
                self.lgr.debug(f"\tWord:  [{word.word_idx}] {word.text}")
                if (marker is not None) and (word.word_idx == marker.word_idx):
                    item_word_lines.append(item_word_line)
                    if m_idx != 0:
                        prev_marker = num_markers[m_idx - 1]
                        li = build_list_item(prev_marker, item_word_lines)
                        self.lgr.debug(f"\t New list_item: {str(li)}")
                        list_items.append(li)
                    item_word_lines, item_word_line, m_idx = [], [], m_idx + 1
                    marker = num_markers[m_idx] if m_idx < len(num_markers) else None
                else:
                    item_word_line.append(word)
            item_word_lines.append(item_word_line)

        if self.has_footer:
            f_text = to_str(item_word_lines)
            self.lgr.debug(f"\tFooter Lines:\n {f_text}\n")
            item_word_lines = self.remove_footer(item_word_lines)
            list_items.append(build_list_item(num_markers[-1], item_word_lines))

        enum_li = enumerate(list_items)
        [self.lgr.debug(f"> Page {page_path} {idx}: {str(li)}") for idx, li in enum_li]

        return list_items

    def find_markers(self, page, word_lines):
        ws = page.words_in_xrange(self.x_range, partial=True)
        print(f'x_range: {self.x_range} {len(ws)}')
        ws = [w for w in ws if w.box.in_yrange(self.y_range, partial=False)]

        ws = [w for w in ws if len(w.text) >= 1 and not w.text.isupper()]

        print(f'marker_words[{len(ws)}:{", ".join(w.text for w in ws)}')
        line_idxs = [-1] * len(page.words)
        for line_idx, wline in enumerate(word_lines):
            for w in wline:
                line_idxs[w.word_idx] = line_idx

        line_marker_dict = {}
        for w in ws:
            line_idx = line_idxs[w.word_idx]
            line_marker_dict.setdefault(line_idx, []).append(w)

        result_ws = []
        sorted_line_idxs = sorted(line_marker_dict.keys())
        for line_idx in sorted_line_idxs:
            line_words = sorted(line_marker_dict[line_idx], key=lambda w: w.xmin)
            result_ws.append(line_words[0])

        print(f'marker_words[{len(result_ws)}:{", ".join(w.text for w in result_ws)}')
        return result_ws

    def get_arranged_word_lines(self, page):
        wl_idxs = page.arranged_word_lines_idxs
        return [[page.words[idx] for idx in wl] for wl in wl_idxs]

    def get_rotated_word_lines(self, page, rotation_config):
        def get_num_markers_angle(page):
            import math

            import numpy as np

            num_markers = getattr(page, "num_markers", [])
            if len(num_markers) < self.min_markers_onpage:
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

        strategy = rotation_config["rotation_strategy"]
        assert strategy != "none"

        if strategy == "manual":
            angle = rotation_config["rotation_arg"]
        elif strategy == "num_markers":
            angle = get_num_markers_angle(page)
        else:
            angle = 0.0
            # pass check rotation detector

        if abs(angle) > rotation_config["rotation_min_angle"]:
            self.lgr.info(f"Rotated page {page.page_idx} strategy: {strategy} angle: {angle}")
            rota_page = Page.build_rotated(page, angle)
            rota_word_lines = words_in_lines(rota_page)
            result_word_lines = []
            for rota_wl in rota_word_lines:
                result_wl = [page.words[rota_w.word_idx] for rota_w in rota_wl]
                result_word_lines.append(result_wl)
            return result_word_lines
        else:
            return words_in_lines(page)

    def get_rotation_config(self, doc_config):
        r_config = doc_config.get("rotation_config", self.rotation_config)
        if len(r_config) == len(self.rotation_config):
            return r_config

        # Todo explore dictionary merge
        for (key, value) in self.rotation_config.items():
            if key not in r_config:
                r_config[key] = doc_config.get(key, value)
        return r_config

    def __call__(self, doc):
        def rotate_page(page, rotation_config):
            if rotation_config["rotation_strategy"] == "none":
                return False
            elif page.page_idx in rotation_config["rotation_page_idxs"]:
                return True
            return False

        self.add_log_handler(doc)
        self.lgr.info(f"list_finder: {doc.pdf_name}")

        doc_config = load_config(self.doc_confdir, doc.pdf_name, "listfinder")

        old_fhm = self.footer_height_multiple
        self.footer_height_multiple = doc_config.get("footer_height_multiple", old_fhm)

        old_page_idxs = self.page_idxs
        self.page_idxs = doc_config.get('page_idxs', self.page_idxs)
        self.page_idxs = parse_range(self.page_idxs)
        print('Page_idxs: {self.page_idxs}')

        old_y_range = self.y_range
        self.y_range = doc_config.get('y_range', self.y_range)

        rotation_config = self.get_rotation_config(doc_config)

        doc.add_extra_page_field("list_items", ("list", __name__, "ListItem"))
        for page_idx, page in enumerate(doc.pages):
            if page_idx not in self.page_idxs:
                page.list_items = []
                continue

            if hasattr(page, "arranged_word_lines_idxs"):
                word_lines = self.get_arranged_word_lines(page)
            elif rotate_page(page, rotation_config):
                word_lines = self.get_rotated_word_lines(page, rotation_config)
            else:
                nl_ht_multiple = doc_config.get("newline_height_multiple", 1.0)
                word_lines = words_in_lines(page, newline_height_multiple=nl_ht_multiple)

            # Move this to the top and save some words lines methods
            word_markers = self.find_markers(page, word_lines)
            print(f'Page {page_idx}: {len(word_markers)}')
            page.list_items = self.find_inpage(word_lines, word_markers, page.page_idx)

        self.footer_height_multiple = old_fhm
        self.page_idxs = old_page_idxs
        self.y_range = old_y_range

        self.remove_log_handler(doc)
        return doc


# b /Users/mukund/Software/docInt/docint/pipeline/list_finder.py:268
