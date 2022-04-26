from typing import List
import logging
import sys
from pathlib import Path
from collections import Counter
import string
import calendar

from more_itertools import first

from ..vision import Vision
from ..word_line import words_in_lines


from ..extracts.orgpedia import Officer, OrderDetail
from ..util import find_date, load_config
from ..region import DataError, UnmatchedTextsError


    

@Vision.factory(
    "order_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "orderbuilder", ## TODO pleae change this.
        "pre_edit": True,
        "ignore_texts": '',
        "ignore_texts_file": ''
    },
)
class OrderBuilder:
    def __init__(self, conf_dir, conf_stub, pre_edit, ignore_texts, ignore_texts_file):
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub
        self.pre_edit = pre_edit
        self.ignore_texts = ignore_texts.split('-')
        self.ignore_texts_file = Path(ignore_texts_file) if ignore_texts_file else None
        
        self.color_config = {
            'person': 'white on yellow',
            'post-dept-continues': 'white on green',
            'post-dept-relinquishes': 'white on spring_green1',
            'post-dept-assumes': 'white on dark_slate_gray1',
            'dept': 'white on spring_green1',
            'department': 'white on spring_green1',            
            
            'post-role-continues': 'white on red',
            'post-role-relinquishes': 'white on magenta',
            'post-role-assumes': 'white on purple',
            'role': 'white on red',
            'verb': 'white on black'
            
        }
        if self.ignore_texts_file:
            self.ignore_texts_from_file = self.ignore_texts_file.read_text().split('\n')
            self.ignore_texts_from_file = [t.lower() for t in self.ignore_texts_from_file]
            print(f'Read {len(self.ignore_texts_from_file)} texts')
        else:
            self.ignore_texts_from_file = []

        self.ignore_texts = [t.lower() for t in self.ignore_texts]
            
        self.ignore_unmatched = set(['the', 'of', 'office', 'charge', 'and', 'will', 'he', 'additional', '&', 'has', 'offices', 'also', 'to', 'be', 'uf', 'continue', 'addition', 'she', 'other', 'hold', 'temporarily', 'assist',  'held', 'his', 'in', 'that', '(a)', '(b)', 'temporary', 'as', 'or', 'with', 'effect', 'holding', 'allocated', 'duties', 'been', 'after', 'under', 'of(a)', 'and(b)', 'and(c)', 'him', 'till', 'recovers', 'fully', 'look', 'work', 'from', 'th', 'june', '1980', 'for', 'time', 'being', ')', '(', '/', 'by', 'portfolio', 'discharge', 'assisting', 'hereafter', 'designated'] + self.ignore_texts + self.ignore_texts_from_file)

        
        self.unmatched_ctr = Counter()


        
        ignore_puncts = string.punctuation
        self.punct_tbl = str.maketrans(
            ignore_puncts, " " * len(ignore_puncts)
        )
        self.month_names = list(calendar.month_name) + list(calendar.month_abbr)
        self.month_names = [m.lower() for m in self.month_names]


        self.lgr = logging.getLogger(__name__)
        self.lgr.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)
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

    def get_salut(self, name):
        short = 'capt-col-dr.(smt.)-dr. (smt.)-dr. (shrimati)-dr-general (retd.)-general-km-kum-kumari-maj. gen. (retd.)-maj-miss-ms-prof. (dr.)-prof-sadhvi-sardar-shri-shrimati-shrinati-shrl-shrt-shr-smt-sushree-sushri'

        saluts = []
        for s in short.split("-"):
            p = f"{s} .-{s} -{s}. -({s}) -({s}.) -({s}.)-{s}."
            saluts.extend(p.split("-"))

        name_lower = name.lower()
        found_salut = first([s for s in saluts if name_lower.startswith(s)], "")
        result = name[:len(found_salut)]
        return result


    def build_detail(self, list_item, post_info, detail_idx):
        person_spans = list_item.get_spans("person")

        is_valid = False if len(person_spans) != 1 else True

        if person_spans:
            person_span = person_spans[0]
            officer_words = list_item.get_words_in_spans([person_span])
            
            full_name = list_item.get_text_for_spans([person_span])
            full_name = full_name.strip(".|,-*():%/1234567890$ '")
            salut = self.get_salut(full_name)
            name = full_name[len(salut):]

            if ',' in name:
                print(f'Replacing comma {officer_text}')
                name = name.replace(',', '')

            
            officer = Officer.build(officer_words, salut, name, cadre='goi_minister')
            order_detail = OrderDetail.build(
                list_item.words, officer, post_info, detail_idx
            )
            #order_detail.extra_spans = person_spans[1:]
            order_detail.is_valid = is_valid
            return order_detail
        else:
            return None


    def get_order_date(self, doc):
        # TODO STOP this word merging outside region !!

        order_date = doc.pages[0].layoutlm.get('ORDERDATEPLACE', [])
        word_lines = words_in_lines(order_date, para_indent=False)

        for word_line in word_lines:
            date_line = ' '.join(w.text for w in word_line)
            dt, err_msg = find_date(date_line)
            if dt and (not err_msg):
                return dt
        return ""

    def get_order_number(self, doc):
        order_number = doc.pages[0].layoutlm.get('HEADER', [])
        word_lines = words_in_lines(order_number, para_indent=False)
        for word_line in word_lines:
            if word_line:
                first_line = ' '.join(w.text for w in word_line)
                return first_line
        return ''

    def process_unmatched(self, unmatched_texts):
        def is_date_or_digit(text):
            if text.isdigit():
                return True
            
            if text.lower() in self.month_names:
                return True

            for date_ext in ['rd', 'st', 'nd', 'th']:
                if text.lower().rstrip(date_ext + ' ').strip().isdigit():
                    return True

            if text.isdigit():
                return True
            
            return False

        def is_all_punct(text):
            text = text.translate(self.punct_tbl).strip()
            return False if text else True

        u_texts = [t for t in unmatched_texts if t.lower() not in self.ignore_unmatched]
        u_texts = [t for t in u_texts if not is_date_or_digit(t) ]
        u_texts = [t for t in u_texts if not is_all_punct(t) ]
        return u_texts

    def test(self, list_item, order_detail, post_info, detail_idx):
        list_item_text = list_item.line_text()
        
        #ident_str = f'{list_item.doc.pdf_name}:{list_item.page.page_idx}>{detail_idx}'
        edit_str = '|'.join([f'{e}' for e in list_item.edits])

        person_spans = list_item.get_spans('person')
        person_str = person_spans[0].span_str(list_item_text) if person_spans else ''

        
        errors = list_item.errors +  post_info.errors
        errors += order_detail.errors if order_detail is not None else []

        #u_texts = [ t.lower() for t in list_item.get_unlabeled_texts() if t.lower() not in self.ignore_unmatched ]
        u_texts = self.process_unmatched(list_item.get_unlabeled_texts())
        if u_texts:
            errors.append(UnmatchedTextsError.build('{detail_idx}', u_texts))

        # u_texts_str = ' '.join(u_texts)
        # if not ('minis' in u_texts_str or 'depa' in u_texts_str):
        #     return []

        self.lgr.debug(list_item.orig_text())            
        self.lgr.debug(f'{"edits":13}: {edit_str}')
        self.lgr.debug(f'{"person":13}: {person_str}')
        self.lgr.debug(str(post_info))        
        if errors:
            self.lgr.debug('Error')
            list_item.print_color_idx(self.color_config, width=150)
            for e in errors:
                self.lgr.debug(f'\t{str(e)}')
        self.lgr.debug('------------------------')
        return errors
                

    def __call__(self, doc):
        self.add_log_handler(doc)        
        self.lgr.info(f"order_builder: {doc.pdf_name}")
        doc.add_extra_field('order_details', ('list', 'docint.extracts.orgpedia', 'OrderDetail'))        
        doc.add_extra_field("order", ("obj", 'docint.extracts.orgpedia', 'Order'))        

        if self.pre_edit:
            doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)
            edits = doc_config.get("edits", [])
            if edits:
                print(f'Edited document: {doc.pdf_name}')
                doc.edit(edits)

        # TODO these need to be regions so that lineage exists
        doc.order_date = self.get_order_date(doc)
        doc.order_number = self.get_order_number(doc)

        self.lgr.debug(f'*** order_date:{doc.order_date}')
        self.lgr.debug(f'*** order_number:{doc.order_number}')

        doc.order_details, detail_idx, errors = [], 1, []
        for page in doc.pages:
            list_items = getattr(page, 'list_items', [])            
            assert len(list_items) == len(page.post_infos)
            en_list_post = enumerate(zip(list_items, page.post_infos))            
            for (idx, (list_item, post_info)) in en_list_post:
                if post_info.is_valid:
                    order_detail = self.build_detail(list_item, post_info, detail_idx)
                    if order_detail:
                        print(order_detail.to_str())
                        doc.order_details.append(order_detail)
                        detail_idx += 1
                    errors += self.test(list_item, order_detail, post_info, idx)
                else:
                    errors += self.test(list_item, None, post_info, idx)

        
        self.lgr.info(f"=={doc.pdf_name}.order_builder {len(doc.order_details)} {DataError.error_counts(errors)}")        
        self.remove_log_handler(doc)        
        return doc
