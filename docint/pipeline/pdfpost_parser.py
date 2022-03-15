import sys
from typing import List
import logging
from pathlib import Path
from textwrap import wrap
from operator import attrgetter

from ..vision import Vision
from ..hierarchy import Hierarchy, MatchOptions
from ..region import Region, TextConfig, DataError
from ..extracts.orgpedia import Post
from ..span import Span

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


    def build_post(self, hier_sg_dict, post_words, post_str, detail_idx):
        def get_role(role_sgs):
            sgs = [sg for sg in role_sgs if sg.full_span.start == 0]
            return sgs[0] if len(sgs) == 1 else None

        def get_dept(dept_sgs):
            dept_sgs.sort(key=attrgetter('sum_span_len'), reverse=True)
            return dept_sgs[0] if dept_sgs else None

        def get_juri(juri_sgs):
            juri_sgs.sort(key=attrgetter('sum_span_len'), reverse=True)
            return juri_sgs[0] if juri_sgs else None

        def get_loca(loca_sgs):
            txts_sgs = [ (Span.to_str(post_str, sg), sg) for sg in loca_sgs ]
            txts_sgs.sort(key=lambda tup: len(tup[0]), reverse=True)
            return txts_sgs[0] if txts_sgs else None

        def get_stat(stat_sgs):
            return stat_sgs[0] if stat_sgs else None

        post_dict = {}
        for (field, span_groups) in hier_sg_dict.items():
            proc = f'get_{field}'
            field_sg = locals()[proc](span_groups)

        post = Post.build(post_words, post_str, *post_dict)
        return post


    def parse(self, post_words, post_str, detail_idx):
        match_paths_dict = {}
        self.lgr.info(f'>{post_str}')
        for (field, hierarchy) in self.hierarchy_dict.items():
            try:
                match_paths = hierarchy.find_match_paths(post_str, self.match_options)
            except Exception as e:
                self.lgr.info(f'\t{field}: PARSE FAILED {post_str}')
                match_paths = []
            else:
                match_paths_dict[field] = match_paths
                n = len(match_paths)
                self.lgr.info(f"\t{field}[{n}]: {Hierarchy.to_str(match_paths)}")
        # end for

        post = self.build_post(match_paths_dict, post_words, post_str, detail_idx)
        return post
        
        #post_info = self.build_post_info(post_words, match_paths_dict, detail_idx)

    def __call__(self, doc):
        self.add_log_handler(doc)        
        self.lgr.info(f"post_parser: {doc.pdf_name}")
        
        doc.add_extra_page_field("posts", ("list", "docint.extracts.orgpedia", "Post"))
        header_info = doc.header_info
        stub_idx, loca_idx = header_info.index('post_stub'), header_info.index('loca')

        for page_idx, page in enumerate(doc.pages):
            page.posts = []
            if not page.tables:
                continue
            assert len(page.tables) == 1, f'Multiple tables {doc.pdf_name} {page_idx}'
            for (detail_idx, row) in enumerate(page.tables[0].body_rows):
                stub_c, loca_c = row.cells[stub_idx], row.cells[loca_idx]
                stub, loca = stub_c.raw_text(), loca_c.raw_text()
                stubL, locaL = stub.lower(), loca.lower()
                post_str = stub if stubL.endswith(locaL) else f'{stub} {loca}'
                post_words = stub_c.words + loca_c.words
                
                post = self.parse(post_words, post_str, detail_idx)
                page.posts.append(post)
        self.remove_log_handler(doc)                
        return doc

    def __del__(self):
        print('DELETING')
        record_dir = Path('/tmp/record')
        for field, file_name in self.hierarchy_files.items():
            hierarchy_path = record_dir / file_name
            #self.hierarchy_dict[field].write_record(hierarchy_path)
        




