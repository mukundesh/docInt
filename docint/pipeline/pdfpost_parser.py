import sys
from typing import List
import logging
from pathlib import Path
from textwrap import wrap

from ..vision import Vision
from ..hierarchy import Hierarchy, MatchOptions
from ..region import Region, TextConfig, DataError
from ..extracts.orgpedia import Post

from ..util import read_config_from_disk


@Vision.factory(
    "pdfpost_parser",
    default_config={
        "doc_confdir": "conf",
        "hierarchy_files": {
            "dept": "dept.yml",
            "role": "role.yml",
            "juri": "juri.yml",
            "loca": "loca.yml",
            "stat": "stat.yml",                        
        },
        "ignore_labels": ["ignore"],
        "conf_stub": "postparser"
    },
)
class PostParser:
    def __init__(
            self, doc_confdir, hierarchy_files, ignore_labels, conf_stub
    ):
        self.doc_confdir = Path(doc_confdir)
        self.hierarchy_files = hierarchy_files
        self.ignore_labels = ignore_labels
        self.conf_stub = conf_stub

        self.hierarchy_dict = {}
        for field, file_name in self.hierarchy_files.items():
            hierarchy_path = self.doc_confdir / file_name
            hierarchy = Hierarchy(hierarchy_path)
            self.hierarchy_dict[field] = hierarchy

        self.match_options = MatchOptions(ignore_case=True)
        self.text_config = TextConfig(rm_labels=self.ignore_labels)

        self.lgr = logging.getLogger(__name__ + ".")
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


    def parse(self, post_words, post_str, detail_idx):
        match_paths_dict = {}
        #self.lgr.info(f"SpanGroups:\n----------")
        self.lgr.info(post_str)
        for (field, hierarchy) in self.hierarchy_dict.items():
            try:
                match_paths = hierarchy.find_match_paths(post_str, self.match_options)
            except Exception as e:
                self.lgr.info(f'\t{field}: PARSE FAILED {sys.exc_info()[0]}')
                match_paths = []
            else:
                match_paths_dict[field] = match_paths
                n = len(match_paths)
                self.lgr.info(f"\t{field}[{n}]: {Hierarchy.to_str(match_paths)}")
        # end for
        return None
        
        #post_info = self.build_post_info(post_words, match_paths_dict, detail_idx)

    def __call__(self, doc):
        self.add_log_handler(doc)        
        self.lgr.info(f"post_parser: {doc.pdf_name}")
        
        doc.add_extra_page_field("post_infos", ("list", __name__, "PostInfo"))
        header_info = doc.header_info
        stub_idx, loca_idx = header_info.index('post_stub'), header_info.index('loca')
        for page_idx, page in enumerate(doc.pages):
            page.post_infos = []
            if not page.tables:
                continue
            assert len(page.tables) == 1, f'Multiple tables {doc.pdf_name} {page_idx}'
            for (detail_idx, row) in enumerate(page.tables[0].body_rows):
                stub_c, loca_c = row.cells[stub_idx], row.cells[loca_idx]
                stub, loca = stub_c.raw_text(), loca_c.raw_text()
                stubL, locaL = stub.lower(), loca.lower()
                post_str = stub if stubL.endswith(locaL) else f'{stub} {loca}'
                post_words = stub_c.words + loca_c.words
                
                post_info = self.parse(post_words, post_str, detail_idx)
                page.post_infos.append(post_info)
        self.remove_log_handler(doc)                
        return doc



