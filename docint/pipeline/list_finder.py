import logging
import statistics
import sys
from pathlib import Path
from enum import Enum

from ..word_line import words_in_lines
from ..vision import Vision
from ..region import Region
from ..util import load_config
from .num_marker import NumMarker, NumType

class ListItem(Region):
    marker: 'NumMarker'

    @classmethod
    def build(cls, marker, item_word_lines):
        words = [w for wl in item_word_lines for w in wl]
        list_item = ListItem(words=words, word_lines=item_word_lines, marker=marker)
        # print('----------')
        # print(f'{marker.text}')
        # print(list_item.line_text())
        # print('----------')        
        return list_item
    
    
    # def __init__(self, marker, item_word_lines):
    #     words = [w for wl in item_word_lines for w in wl]
    #     super().__init__(words, word_lines=item_word_lines)
        
    #     self.marker = marker
    #     print(f'Marker: {marker.text}')
    #     print(f'list: {self.text}')        
        


@Vision.factory(
    "list_finder",
    default_config={
        "doc_confdir": "conf",
        "pre_edit": True,
        "find_ordinal": True,
        "find_roman": True,
        "find_alphabet": False,
        "min_markers_onpage": 1,
        "has_footer": True,
        "footer_delim": ".,;",
        "footer_height_multiple": 2.0,
    },
)
class ListFinder:
    def __init__(
        self,
        doc_confdir,
        pre_edit,
        find_ordinal,
        find_roman,
        find_alphabet,
        min_markers_onpage,
        has_footer,
        footer_delim,
        footer_height_multiple,
    ):
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.find_ordinal = find_ordinal
        self.find_roman = find_roman
        self.find_alphabet = find_alphabet
        self.min_markers_onpage = min_markers_onpage
        self.has_footer = has_footer
        self.footer_delim = footer_delim
        self.footer_height_multiple = footer_height_multiple
        self.conf_stub = 'listfinder'

        self.lgr = logging.getLogger(f'docint.pipeline.{self.conf_stub}')
        self.lgr.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)
        self.file_handler = None

    def add_log_handler(self, doc):
        handler_name = f'{doc.pdf_name}.{self.conf_stub}.log'
        log_path = Path('logs') / handler_name
        self.file_handler = logging.FileHandler(log_path, mode='w')
        self.lgr.info(f'adding handler {log_path}')

        self.file_handler.setLevel(logging.DEBUG)        
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None
        
        

    def remove_footer(self, word_lines):
        last_word_lines = []
        footer_delim_tuple = tuple(self.footer_delim)
        avg_height = statistics.mean([w.box.height for wl in word_lines for w in wl])
        height_cutoff = avg_height * self.footer_height_multiple

        prev_ymin = -1.0
        for word_line in [wl for wl in word_lines if wl]:
            ymin = statistics.mean([w.box.ymin for w in word_line])
            if prev_ymin != -1.0 and (ymin - prev_ymin) > height_cutoff:
                break
            prev_ymin = ymin

            line_text = " ".join(w.text for w in word_line if w.text)
            
            self.lgr.debug(f'footer adding: {line_text}')
            last_word_lines.append(word_line)

            if line_text.strip().endswith(footer_delim_tuple):
                break
        return last_word_lines

    def find_inpage(self, word_lines, num_markers):
        # assumption that word_lines and num_markers are similarly ordered.
        list_items = []
        item_word_lines, m_idx, marker = [], 0, num_markers[0]
        for word_line in word_lines:
            item_word_line = []
            for word in word_line:
                if (marker is not None) and (word.word_idx == marker.word_idx):
                    item_word_lines.append(item_word_line)
                    if m_idx != 0:
                        prev_marker = num_markers[m_idx-1]
                        list_items.append(ListItem.build(prev_marker, item_word_lines))
                    item_word_lines, item_word_line, m_idx = [], [], m_idx + 1
                    marker = num_markers[m_idx] if m_idx < len(num_markers) else None
                else:
                    item_word_line.append(word)
            item_word_lines.append(item_word_line)
        if self.has_footer:
            item_word_lines = self.remove_footer(item_word_lines)
            list_items.append(ListItem.build(num_markers[-1], item_word_lines))

        return list_items

    def filter_markers(self, markers):
        filtered_markers = []
        for marker in markers:
            if marker.num_type == NumType.Ordinal:
                if  self.find_ordinal:
                    filtered_markers.append(marker)
            elif marker.num_type == NumType.Roman:
                if self.find_roman:
                    filtered_markers.append(marker)
            elif marker.num_type == NumType.Alphabet:
                if self.find_alphabet:
                    filtered_markers.append(marker)

        print(f'Num: {len(filtered_markers)}')
        return filtered_markers

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"list_finder: {doc.pdf_name}")
        
        doc_config = load_config(self.doc_confdir, doc.pdf_name, "listfinder")

        doc.add_extra_page_field('list_items', ('list', __name__, 'ListItem'))
        for page in doc.pages:
            nl_ht_multiple = doc_config.get('newline_height_multiple', 1.0)
            word_lines = words_in_lines(page, newline_height_multiple=nl_ht_multiple)
            num_markers = self.filter_markers(page.num_markers)
            if len(num_markers) > self.min_markers_onpage:
                page.list_items = self.find_inpage(word_lines, num_markers)
            else:
                page.list_items = []
        self.remove_log_handler(doc)
        return doc
