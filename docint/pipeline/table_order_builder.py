import logging
import sys
from itertools import chain
from pathlib import Path
import operator as op

from enchant import request_pwl_dict

from ..vision import Vision
from ..table import TableEmptyBodyCellError, TableMismatchColsError
from ..hierarchy import Hierarchy, MatchOptions
from ..region import DataError, UnmatchedTextsError
from ..extracts.orgpedia import OrderDetail, Post, Officer
from ..span import Span


@Vision.factory(
    "table_order_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "tableorder",
        "hierarchy_files": {
            "dept": "dept.yml",
            "role": "role.yml",
        },
        "dict_file": "output/pwl_words.txt",
        "unicode_file": "conf/unicode.txt",
    },
)
class TableOrderBuidler:
    def __init__(self, conf_dir, conf_stub, hierarchy_files, dict_file, unicode_file):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = conf_stub
        self.hierarchy_files = hierarchy_files
        self.dict_file = dict_file
        self.unicode_file = unicode_file
        
        self.hierarchy_dict = {}
        for field, file_name in self.hierarchy_files.items():
            hierarchy_path = self.conf_dir / file_name
            hierarchy = Hierarchy(hierarchy_path)
            self.hierarchy_dict[field] = hierarchy
        self.match_options = MatchOptions(ignore_case=True)
        
        self.dict_file = dict_file
        self.unicode_file = unicode_file

        self.ignore_unmatched = set(["of", "the"])
        self.dictionary = request_pwl_dict(str(self.dict_file))        

        self.lgr = logging.getLogger(f'docint.pipeline.{self.conf_stub}')
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

    def get_officer(self, officer_cell, path):
        errors = []
        if not officer_cell:
            msg = "empty cell"
            errors.append(TableEmptyBodyCellError(path=path, msg=msg, is_none=True))

        officer_text = officer_cell.line_text()
        d_texts = [t for t in officer_text.split() if self.dictionary.check(t)]

        if d_texts:
            msg = 'found text: {",".join(dictionary_texts)}'
            #errors.append(DictionaryTextFound(path=path, msg=msg))

        officer = Officer.build(officer_cell.words, '', officer_text)
        return officer, errors

    def get_posts(self, post_cell, path):
        posts, errors = [], []
        if not post_cell:
            msg = "empty cell"
            errors.append(TableEmptyBodyCellError(path=path, msg=msg, is_none=True))

        post_str, hier_span_groups = post_cell.raw_text(), []
        for (field, hierarchy) in self.hierarchy_dict.items():
            field_sgs = hierarchy.find_match_paths(post_str, self.match_options)
            self.lgr.debug(f"{field}: {Hierarchy.to_str(field_sgs)}")
            hier_span_groups += field_sgs
        hier_span_groups = sorted(hier_span_groups, key=op.attrgetter("min_start"))

        role_sg = None
        for span_group in hier_span_groups:
            if span_group.root == "__department__":
                dept_sg = span_group
                posts.append(Post.build(post_cell.words, post_str, dept_sg, role_sg))
            else:
                role_sg = span_group

        all_spans = list(chain(*[sg.spans for sg in hier_span_groups]))
        
        u_texts = Span.unmatched_texts(all_spans, post_str)
        u_texts = [t.lower() for t in u_texts]
        u_texts = [t for t in u_texts if t not in self.ignore_unmatched]
        
        if u_texts:
            errors.append(UnmatchedTextsError.build(path, u_texts))
        return posts, errors

    def build_detail(self, row, path, doc_verb, detail_idx):
        errors = []
        if len(row.cells) != 3:
            msg = "Expected: 3 columns Actual: {len(row.cells)}"
            errors.append(TableMismatchColsError(path, msg))

        officer_cell = row.cells[1] if len(row.cells) > 1 else None
        officer, officer_errors = self.get_officer(officer_cell, f"{path}.c1")

        post_cell = row.cells[2] if len(row.cells) > 2 else ""
        posts, post_errors = self.get_posts(post_cell, f"{path}.c2")

        (c, r) = (posts, []) if doc_verb == 'continues' else ([], posts)
        d = OrderDetail(
            words=row.words,
            word_line=[row.words],
            officer=officer,
            continues=c,
            relinquishes=r,
            assumes=[],
            detail_idx=detail_idx,
        )
        all_errors = officer_errors + post_errors
        return d, all_errors

    def iter_rows(self, doc):
        for (page_idx, page) in enumerate(doc.pages):
            for (table_idx, table) in enumerate(page.tables):
                for (row_idx, row) in enumerate(table.body_rows):
                    yield page_idx, table_idx, row_idx, row

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"table_order_builder: {doc.pdf_name}")
        doc.add_extra_field("order_details", ("list", __name__, "OrderDetails"))
        doc.add_extra_field("order", ("obj", __name__, "Order"))

        #doc.order_date = self.get_order_date(doc)
        #doc.order_number = self.get_order_number(doc)

        details, errors = [], []
        self.verb = "continues"  # self.get_verb(doc)
        for page_idx, table_idx, row_idx, row in self.iter_rows(doc):
            path = f"p{page_idx}.t{table_idx}.r{row_idx}"
            detail, d_errors = self.build_detail(row, path, 'continues', row_idx)
            detail.errors = d_errors
            details.append(detail)
            errors.extend(d_errors)
        
        self.lgr.info(f"==Total:{len(errors)} {DataError.error_counts(errors)}")
        self.remove_log_handler(doc)
        return doc
