import logging
import sys
from itertools import chain
from pathlib import Path
import operator as op
from collections import Counter
from string import punctuation
import re

from enchant import request_pwl_dict
import yaml
from more_itertools import first

from ..vision import Vision
from ..table import TableEmptyBodyCellError, TableMismatchColsError
from ..hierarchy import Hierarchy, MatchOptions
from ..region import DataError, UnmatchedTextsError, TextConfig
from ..extracts.orgpedia import OrderDetail, Post, Officer, Order
from ..extracts.orgpedia import IncorrectOfficerNameError, EnglishWordsInNameError
from ..extracts.orgpedia import IncorrectOrderDateError, OrderDateNotFoundErrror


from ..span import Span, SpanGroup
from ..util import read_config_from_disk, find_date

from ..word_line import words_in_lines


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
        "unicode_file": "conf/unicode.yml",
    },
)
class TableOrderBuidler:
    def __init__(self, conf_dir, conf_stub, hierarchy_files, dict_file, unicode_file):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = conf_stub
        self.hierarchy_files = hierarchy_files
        self.dict_file = Path(dict_file)
        self.unicode_file = Path(unicode_file)
        
        self.hierarchy_dict = {}
        for field, file_name in self.hierarchy_files.items():
            hierarchy_path = self.conf_dir / file_name
            hierarchy = Hierarchy(hierarchy_path)
            self.hierarchy_dict[field] = hierarchy
        self.match_options = MatchOptions(ignore_case=True)
        
        yml = read_config_from_disk(self.unicode_file)
        self.unicode_dict = dict((u, a if a != '<ignore>' else '') for u, a in yml.items())

        self.ignore_paren_strs = ['harg', 'depart', 'defence', 'banking', 'indep',
                                  'state', 'indapendent', 'smt .', 'deptt', 'shrimati',
                                  'indap', 'indop']


        ## ADDING DEPARTMENTS
        i = "of-the-and-to-hold-temporary-charge-in-also-not-any-additional-incharge-with-departments-for"
        self.ignore_unmatched = set(i.split('-'))
        self.dictionary = request_pwl_dict(str(self.dict_file))

        self.unmatched_ctr = Counter()
        self.punct_tbl = str.maketrans(punctuation, " " * len(punctuation))

        self.missing_unicode_dict={}

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

    def add_missing_unicodes(self, missing):
        [self.missing_unicode_dict.setdefault(k, 'missing') for k in missing]

    def get_salut(self, name):
        short = 'capt-col-dr.(smt.)-dr. (smt.)-dr. (shrimati)-dr-general ( retd . )-general (retd.)-general-km-kum-kumari-maj. gen. (retd.)-maj-miss-ms-prof. (dr.)-prof-sadhvi-sardar-shri-shrimati-shrinati-shrl-shrt-shr-smt-sushree-sushri'

        saluts = []
        for s in short.split("-"):
            p = f"{s} .-{s} -{s}. -({s}) -({s}.) -({s}.)-{s}."
            saluts.extend(p.split("-"))

        name_lower = name.lower()
        found_salut = first([s for s in saluts if name_lower.startswith(s)], "")
        result = name[:len(found_salut)]
        return result
        

    def get_officer(self, officer_cell, path):
        errors = []
        if not officer_cell:
            msg = "empty cell"
            errors.append(TableEmptyBodyCellError(path=path, msg=msg, is_none=True))

        missing_unicodes = officer_cell.make_ascii(self.unicode_dict)
        self.add_missing_unicodes(missing_unicodes) # save the missing unicodes

        officer_text = officer_cell.line_text()
        officer_text = officer_text.strip(".|,-*@():%/1234567890$ '")

        if missing_unicodes:
            print(f'Unicode: {officer_text}: {missing_unicodes}')


        # check if there are english words
        englist_texts = []
        for text in officer_text.split():
            text = text.strip('()')
            if text and self.dictionary.check(text):
                if text.isupper():
                    officer_text = officer_text.replace(text, '')
                else:
                    englist_texts.append(text)
                    
        if englist_texts:
            if 'Deputy Prime Minister' in officer_text:
                officer_text = officer_text.replace('Deputy Prime Minister', '')
                
            eng_str = ','.join(englist_texts)
            msg = f'English words in officer name: >{eng_str}<'
            errors.append(EnglishWordsInNameError(msg=msg, path=path))

        if len(officer_text) < 10 or len(officer_text) > 45:
            msg = f'Short officer name: >{officer_text}<'
            errors.append(IncorrectOfficerNameError(msg=msg, path=path))

        if ',' in officer_text:
            print(f'Replacing comma {officer_text}')
            officer_text = officer_text.replace(',', '.')

        salut = self.get_salut(officer_text)
        name = officer_text[len(salut):].strip()

        officer = Officer.build(officer_cell.words, salut, name, cadre='goi_minister')
        return officer, errors

    def get_paren_spans(self, post_str, ignore_paren_len=5, ):
        paren_spans = []
        for m in re.finditer(r'\((.*?)\)', post_str):
            mat_str = m.group(1).lower()
            if len(mat_str) < ignore_paren_len:
                continue
            elif any([sl in mat_str for sl in self.ignore_paren_strs]):
                continue
            else:
                s, e = m.span()
                self.lgr.debug(f'BLANKPAREN: {m.group(0)} ->[{s}: {e}]')
                paren_spans.append(Span(start=s, end=e))
        return paren_spans

    def get_allcaps_spans(self, post_str):
        allcaps_spans = []
        for m in re.finditer(r'\S+', post_str):
            mat_str = m.group(0).strip('()')
            if mat_str.isupper() and len(mat_str) > 1 and '.' not in mat_str:
                s, e = m.span()
                allcaps_spans.append(Span(start=s, end=e))
                
        allcaps_spans = Span.accumulate(allcaps_spans, post_str)
        return allcaps_spans
    

    def get_posts(self, post_cell, path):
        posts, errors = [], []
        if not post_cell:
            msg = "empty cell"
            errors.append(TableEmptyBodyCellError(path=path, msg=msg, is_none=True))

        self.lgr.debug(f'Before: {post_cell.line_text()}')
        
        missing_unicodes = post_cell.make_ascii(self.unicode_dict)
        self.add_missing_unicodes(missing_unicodes) # save the missing unicodes
        
        ignore_config = TextConfig(rm_labels=['ignore'])
        post_str = post_cell.line_text(ignore_config)
        
        paren_spans = self.get_paren_spans(post_str)
        [ post_cell.add_span(s.start, s.end, 'ignore', ignore_config) for s in paren_spans ]

        post_str = post_cell.line_text(ignore_config)
        allcaps_spans = self.get_allcaps_spans(post_str)
        [ post_cell.add_span(s.start, s.end, 'ignore', ignore_config) for s in allcaps_spans ]
        if allcaps_spans:
            print(f'Removed Before >{post_str}<')
            print(f'Removed After  >{post_cell.line_text(ignore_config)}')

        
        
        post_cell.merge_words(self.dictionary, ignore_config)
        post_cell.correct_words(self.dictionary, ignore_config)
        post_cell.mark_regex([r'[.,;\']', 'in the'], 'ignore', ignore_config)

        self.lgr.debug(f'After: {post_cell.line_text(ignore_config)}')        

        post_str, hier_span_groups = post_cell.line_text(ignore_config), []
        ## replacing double space
        post_str = post_str.replace('  ', ' ')
        self.lgr.debug(f"{post_str}")
        
        dept_sgs = self.hierarchy_dict['dept'].find_match(post_str, self.match_options)
        self.lgr.debug(f"dept: {Hierarchy.to_str(dept_sgs)}")
        
        b_post_str = SpanGroup.blank_text(dept_sgs, post_str)
        role_sgs = self.hierarchy_dict['role'].find_match(b_post_str, self.match_options)
        self.lgr.debug(f"role: {Hierarchy.to_str(role_sgs)}")
        
        hier_span_groups = dept_sgs + role_sgs
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
        
        u_texts = [t.lower() for ts in u_texts for t in ts.strip().split()]
        u_texts = [t.translate(self.punct_tbl).strip() for t in u_texts]
        u_texts = [t for t in u_texts if t]
        u_texts = [t for t in u_texts if t not in self.ignore_unmatched]
        u_texts = [t for t in u_texts if not t.isdigit()]
        
        if u_texts:
            self.unmatched_ctr.update(u_texts)
            errors.append(UnmatchedTextsError.build(path, u_texts, post_str))
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
        
        word_idxs = [w.word_idx for w in row.words]
        page_idx = row.words[0].page_idx if row.words else None
        
        d = OrderDetail(
            words=row.words,
            word_line=[row.words],
            word_idxs=word_idxs,
            page_idx_=page_idx,
            word_lines_idxs=[word_idxs],            
            officer=officer,
            continues=c,
            relinquishes=r,
            assumes=[],
            detail_idx=detail_idx,
        )
        d.errors = officer_errors + post_errors
        print('--------')
        print(d.to_str())
        all_errors = officer_errors + post_errors
        return d, all_errors

    def get_order_date(self, doc):
        result_dt, errors, date_text = None, [], ''
        if not getattr(doc.pages[0], 'layoutlm', None):
            path = 'pa0.layoutlm'
            msg = f"layoutlm not found !"
            errors.append(OrderDateNotFoundErrror(path=path, msg=msg))
            return None, errors
        
        order_date = doc.pages[0].layoutlm.get('ORDERDATEPLACE', [])
        word_lines = words_in_lines(order_date, para_indent=False)

        for word_line in word_lines:
            date_line = ' '.join(w.text for w in word_line)
            print(f'DL: {date_line}')            
            if len(date_line) < 10:
                date_text += ' '.join(f'{w.word_idx}:{w.text}' for w in word_line)
                continue
            
            dt, err_msg = find_date(date_line)
            if dt and (not err_msg):
                result_dt = dt
                date_text += ' '.join(f'{w.word_idx}:{w.text}' for w in word_line)
                break
            date_text += ' '.join(f'{w.word_idx}:{w.text}' for w in word_line)
            
        if result_dt and (result_dt.year < 1947 or result_dt.year > 2021):
            path = 'pa0.layoutlm.ORDERDATEPLACE'
            msg = f'Incorrect date: {result_dt} in {date_text}'
            errors.append(IncorrectOrderDateError(path=path, msg=msg))
        elif result_dt is None:
            path = 'pa0.layoutlm.ORDERDATEPLACE'
            msg = f"text: >{date_text}<" 
            errors.append(OrderDateNotFoundErrror(path=path, msg=msg))

        print(f'Order Date: {result_dt}')
        return result_dt, errors
        
    

    def iter_rows(self, doc):
        for (page_idx, page) in enumerate(doc.pages):
            for (table_idx, table) in enumerate(page.tables):
                for (row_idx, row) in enumerate(table.body_rows):
                    yield page_idx, table_idx, row_idx, row

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"table_order_builder: {doc.pdf_name}")
        #doc.add_extra_field("order_details", ("list", "docint.extracts.orgpedia", "OrderDetail"))
        
        doc.add_extra_field("order", ("obj", "docint.extracts.orgpedia", "Order"))

        #doc.order_number = self.get_order_number(doc)
        order_details, errors = [], []
        
        order_date, date_errors = self.get_order_date(doc)
        errors.extend(date_errors)
        
        self.verb = "continues"  # self.get_verb(doc)
        for page_idx, table_idx, row_idx, row in self.iter_rows(doc):
            path = f"p{page_idx}.t{table_idx}.r{row_idx}"
            detail, d_errors = self.build_detail(row, path, 'continues', row_idx)
            detail.errors = d_errors
            order_details.append(detail)
            errors.extend(d_errors)

        doc.order = Order.build(doc.pdf_name, order_date, doc.pdffile_path, order_details)
        doc.order.category = 'Council'
        
        self.lgr.info(f"=={doc.pdf_name}.table_order_builder {len(doc.order.details)} {DataError.error_counts(errors)}")
        [self.lgr.info(str(e)) for e in errors]        
        
        self.remove_log_handler(doc)
        return doc

    def __del__(self):
        u_word_counts = self.unmatched_ctr.most_common(None)
        self.lgr.info(f'++{"|".join(f"{u} {c}" for (u,c) in u_word_counts)}')
        #Path('/tmp/missing.yml').write_text(yaml.dump(self.missing_unicode_dict), encoding="utf-8")


