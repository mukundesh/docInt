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
        word_idxs = [w.word_idx for w in words]
        page_idx = words[0].page_idx
        word_lines_idxs = [ [w.word_idx for w in wl] for wl in item_word_lines ]
        
        list_item = ListItem(words=words, word_lines=item_word_lines, marker=marker, word_idxs=word_idxs, page_idx_=page_idx, word_lines_idxs=word_lines_idxs)
        # print('----------')
        # print(f'{marker.text}')
        # print(list_item.line_text())
        # print('----------')        
        return list_item

    @property
    def path_abbr(self):
        return f"list_item"

    def __str__(self):
        return self.line_text()
            
    
    
    
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
        def to_str(word_lines):
            return '\n'.join([' '.join(w.text for w in line) for line in word_lines])

        self.lgr.debug(f'** Inside Footer processing')
        last_word_lines = []
        footer_delim_tuple = tuple(self.footer_delim)
        avg_height = statistics.mean([w.box.height for wl in word_lines for w in wl])
        height_cutoff = avg_height * self.footer_height_multiple

        prev_ymin = -1.0
        for word_line in [wl for wl in word_lines if wl]:
            ymin = statistics.mean([w.box.ymin for w in word_line])
            if prev_ymin != -1.0 and (ymin - prev_ymin) > height_cutoff:
                self.lgr.debug(f'line break found {to_str(last_word_lines)}')
                break
            prev_ymin = ymin

            line_text = " ".join(w.text for w in word_line if w.text)
            
            self.lgr.debug(f'footer adding: {line_text}')
            last_word_lines.append(word_line)

            if line_text.strip().endswith(footer_delim_tuple):
                self.lgr.debug(f'end of line {to_str(last_word_lines)}')                
                break
        return last_word_lines

    def find_inpage(self, word_lines, num_markers, page_path):
        def to_str(word_lines):
            return '\n'.join([' '.join(w.text for w in line) for line in word_lines])
        
        # assumption that word_lines and num_markers are similarly ordered.
        list_items = []
        item_word_lines, m_idx, marker = [], 0, num_markers[0]

        self.lgr.debug(f'> Page {page_path} num_markers: {len(num_markers)}')
        for word_line in word_lines:
            item_word_line = []
            for word in word_line:
                self.lgr.debug(f'\tWord:  [{word.word_idx}] {word.text}')
                if (marker is not None) and (word.word_idx == marker.word_idx):
                    item_word_lines.append(item_word_line)
                    if m_idx != 0:
                        prev_marker = num_markers[m_idx-1]
                        li = ListItem.build(prev_marker, item_word_lines)
                        self.lgr.debug(f'\t New list_item: {str(li)}')
                        list_items.append(li)
                    item_word_lines, item_word_line, m_idx = [], [], m_idx + 1
                    marker = num_markers[m_idx] if m_idx < len(num_markers) else None
                else:
                    item_word_line.append(word)
            item_word_lines.append(item_word_line)
            
        if self.has_footer:
            f_text = to_str(item_word_lines)
            self.lgr.debug(f'\tFooter Lines:\n {f_text}\n')            
            item_word_lines = self.remove_footer(item_word_lines)
            list_items.append(ListItem.build(num_markers[-1], item_word_lines))

        enum_li = enumerate(list_items)
        [self.lgr.debug(f'> Page {page_path} {idx}: {str(li)}') for idx, li in enum_li]

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
        
        old_fhm = self.footer_height_multiple
        self.footer_height_multiple = doc_config.get('footer_height_multiple', old_fhm) 

        doc.add_extra_page_field('list_items', ('list', __name__, 'ListItem'))
        for page in doc.pages:
            nl_ht_multiple = doc_config.get('newline_height_multiple', 1.0)
            word_lines = words_in_lines(page, newline_height_multiple=nl_ht_multiple)
            
            num_markers = self.filter_markers(page.num_markers)

            if len(num_markers) > self.min_markers_onpage:
                page.list_items = self.find_inpage(word_lines, num_markers, page.page_idx)
            else:
                page.list_items = []

        self.footer_height_multiple = old_fhm
        self.remove_log_handler(doc)
        return doc
