import logging

from ..vision import Vision
from ..word_line import words_in_lines

from ..extracts.orgpedia import Officer, OrderDetail
from ..util import find_date, load_config


@Vision.factory(
    "order_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "datenumber",
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
            
            'post-role-continues': 'white on red',
            'post-role-relinquishes': 'white on magenta',
            'post-role-assumes': 'white on purple',
            'verb': 'white on black'
            
        }

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler())

    def split_name(self, person_name):
        # TODO
        return "salut", "name"

    def build_detail(self, list_item, post_info, detail_idx):
        person_spans = list_item.get_spans("person")

        is_valid = False if len(person_spans) != 1 else True

        if person_spans:
            full_name = list_item.get_span_text(person_spans[0])
            salut, name = self.split_name(full_name)
            officer_words = list_item.get_span_words(person_spans[0])
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

    def check_detail(self, list_item, order_detail, post_info):
        if not post_info.is_valid:
            err_str = f'{post_info.error}: '
            list_item.print_color(err_str, self.color_config)
            return

        if not order_detail:
            list_item.print_color('PersonError:', self.color_config)
            

    def __call__(self, doc):
        self.logger.info(f"order_builder: {doc.pdf_name}")

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

        print(f'*** order_date:{doc.order_date}')
        print(f'*** order_number:{doc.order_number}')



        doc.order_details, detail_idx = [], 1
        for page in doc.pages:
            assert len(page.list_items) == len(page.post_infos)
            for list_item, post_info in zip(page.list_items, page.post_infos):
                if post_info.is_valid:
                    order_detail = self.build_detail(list_item, post_info, detail_idx)
                    if order_detail:
                        doc.order_details.append(order_detail)
                        detail_idx += 1
                    self.check_detail(list_item, order_detail, post_info)
                else:
                    self.check_detail(list_item, None, post_info)  
        return doc
