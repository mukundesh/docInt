from typing import List
import logging
import sys
from pathlib import Path
from collections import Counter

from ..vision import Vision
from ..word_line import words_in_lines

from ..extracts.orgpedia import Officer, OrderDetail
from ..util import find_date, load_config
from ..region import DataError

class UnmatchedTextsError(DataError):
    texts: List[str]

    @classmethod
    def build(cls, path, unmatched_texts):
        msg = ' '.join(unmatched_texts)
        return UnmatchedTextsError(path=path, msg=msg, texts=unmatched_texts)
    

@Vision.factory(
    "order_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "orderbuilder", ## TODO pleae change this.
        "pre_edit": True,
    },
)
class OrderBuilder:
    def __init__(self, conf_dir, conf_stub, pre_edit):
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub
        self.pre_edit = pre_edit
        self.color_config = {
            'person': 'white on yellow',
            'post-dept-continues': 'white on green',
            'post-dept-relinquishes': 'white on spring_green1',
            'post-dept-assumes': 'white on dark_slate_gray1',
            'dept': 'white on spring_green1',
            
            'post-role-continues': 'white on red',
            'post-role-relinquishes': 'white on magenta',
            'post-role-assumes': 'white on purple',
            'role': 'white on red',
            'verb': 'white on black'
            
        }
        self.ignore_unmatched = set(['the', 'of', 'office', 'charge', 'and', 'will', 'he', 'additional', '&', 'has', 'offices', 'also', 'to', 'be', 'uf', 'continue', 'addition', 'she', 'other', 'hold', 'temporarily', 'assist',  'held', 'his', 'in', 'that', '(a)', '(b)', 'temporary', 'as', 'or', 'with', 'effect', 'holding', 'allocated', 'duties', 'been', 'after', 'under', 'of(a)', 'and(b)', 'and(c)', 'him', 'till', 'recovers', 'fully', 'look', 'work', 'from', 'th', 'june', '1980', 'for', 'time', 'being', ')', '(', '/', 'by', 'portfolio', 'discharge', 'assisting'])
        self.unmatched_ctr = Counter()

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


        
    def split_name(self, person_name):
        # TODO
        return "salut", "name"

    def build_detail(self, list_item, post_info, detail_idx):
        person_spans = list_item.get_spans("person")

        is_valid = False if len(person_spans) != 1 else True

        if person_spans:
            person_span = person_spans[0]
            full_name = list_item.get_text_for_spans([person_span])
            salut, name = self.split_name(full_name)
            officer_words = list_item.get_words_in_spans([person_span])
            officer = Officer.build(officer_words, salut, name)


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

        order_date = doc.pages[0].layoutlm['ORDERDATEPLACE']
        word_lines = words_in_lines(order_date, para_indent=False)

        for word_line in word_lines:
            date_line = ' '.join(w.text for w in word_line)
            dt, err_msg = find_date(date_line)
            if dt and (not err_msg):
                return dt
        return ""

    def get_order_number(self, doc):
        order_number = doc.pages[0].layoutlm['HEADER']
        word_lines = words_in_lines(order_number, para_indent=False)
        for word_line in word_lines:
            if word_line:
                first_line = ' '.join(w.text for w in word_line)
                return first_line
        return ''

    def test(self, list_item, order_detail, post_info, detail_idx):
        list_item_text = list_item.line_text()
        
        #ident_str = f'{list_item.doc.pdf_name}:{list_item.page.page_idx}>{detail_idx}'
        edit_str = '|'.join([f'{e}' for e in list_item.edits])

        person_spans = list_item.get_spans('person')
        person_str = person_spans[0].span_str(list_item_text) if person_spans else ''

        u_texts = [ t.lower() for t in list_item.get_unlabeled_texts() if t.lower() not in self.ignore_unmatched ]
        errors = list_item.errors +  post_info.errors
        errors += order_detail.errors if order_detail is not None else []
        if u_texts:
            errors.append(UnmatchedTextsError.build('{detail_idx}', u_texts))

        u_texts_str = ' '.join(u_texts)
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
        doc.add_extra_field("order_details", ("list", __name__, "OrderDetails"))
        doc.add_extra_field("order", ("obj", __name__, "Order"))

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
            assert len(page.list_items) == len(page.post_infos)
            en_list_post = enumerate(zip(page.list_items, page.post_infos))            
            for (idx, (list_item, post_info)) in en_list_post:
                if post_info.is_valid:
                    order_detail = self.build_detail(list_item, post_info, detail_idx)
                    if order_detail:
                        doc.order_details.append(order_detail)
                        detail_idx += 1
                    errors += self.test(list_item, order_detail, post_info, idx)
                else:
                    errors += self.test(list_item, None, post_info, idx)


        #u_word_counts = self.unmatched_ctr.most_common(None)
        #self.lgr.debug(f'++{"|".join(f"{u} {c}" for (u,c) in u_word_counts)}')
        
        self.lgr.info(f'==Total:{len(errors)} {DataError.error_counts(errors)}')        
        self.remove_log_handler(doc)        
        return doc
