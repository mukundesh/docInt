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


    def get_juri(self, post_str, dept_sg, role_sg, juri_sgs):
        def is_commissioner_role(role_sg):
            return 'Commissioner' in role_sg.hierarchy_path if role_sg else False

        def is_dept_with_juri_label(dept_sg):
            return dept_sg.get_label_val('_juri') is not None if dept_sg else None

        def get_juri_marker(post_str):
            markers = [('DSITT', 'districts'), ('DISTT', 'districts'),
                       ('DISST', 'districts'),
                       ('Range', 'ranges'),]
            for marker,category in markers:
                if marker.lower() in post_str.lower():
                    return category
            return None

        print(f'is_commissioner_role: {is_commissioner_role(role_sg)}')
        print(f'is_dept_with_juri_label: {is_dept_with_juri_label(dept_sg)}')
        print(f'get_juri_marker: {get_juri_marker(post_str)}')
        juriMarker = get_juri_marker(post_str)

        if is_dept_with_juri_label(dept_sg):
            label = dept_sg.get_label_val('_juri')
            sub_path = f'juri.{label}'.lower().split('.')
            juri_hier = self.hierarchy_dict['juri']
            juri_sgs = juri_hier.find_match_in_sub_hierarchy(post_str, sub_path, self.match_options)
            assert len(juri_sgs) == 1
            print(len(juri_sgs))
            return juri_sgs[0]
        elif juriMarker:
            print(f'{juriMarker}, {Hierarchy.to_str(juri_sgs)} {juri_sgs[0].hierarchy_path}')
            juri_sgs = [sg for sg in juri_sgs if sg.spans[0].node.level == juriMarker]
            return juri_sgs[0]
        

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
            return txts_sgs[0][1] if (txts_sgs and txts_sgs[0]) else None

        def get_stat(stat_sgs):
            return stat_sgs[0] if stat_sgs else None

        post_dict = {}
        for (field, span_groups) in hier_sg_dict.items():
            #if field != 'juri':
            proc = f'get_{field}'
            field_sg = locals()[proc](span_groups)
            post_dict[field] = field_sg
            
            #else:
            #    dept_sg, role_sg = post_dict['dept'], post_dict['role']
            #    field_sg = self.get_juri(post_str, dept_sg, role_sg, hier_sg_dict['juri'])
            #post_dict[field] = field_sg
            #self.lgr.info(f"\t{field}: {Hierarchy.to_str([field_sg])}")                                

        post = Post.build(post_words, post_str, **post_dict)
        return post


    def parse(self, post_words, post_str, detail_idx):
        match_paths_dict = {}
        self.lgr.info(f'>{post_str}')
        for (field, hierarchy) in self.hierarchy_dict.items():
            try:
                match_paths = hierarchy.find_match(post_str, self.match_options)
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
        


if __name__ == '__main__':
    hierarchy_files = {
        "dept": "dept.yml",
        "role": "role.yml",
        "juri": "juri.yml",
        "loca": "loca.yml",
        "stat": "stat.yml",                        
    }
    
    post_parser = PostParser("conf", hierarchy_files, ["ignore"], "postparser")

    post_parser.parser([], sys.argv[1],0)



