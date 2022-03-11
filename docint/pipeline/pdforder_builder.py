import logging
import sys

from ..vision import Vision
from ..word_line import words_in_lines

from ..extracts.orgpedia import Officer, OrderDetail
from ..util import find_date, load_config

@Vision.factory(
    "infer_headers",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "mergetables",
        "pre_edit": True,
        "header_dict": {
            "s_no": "num",
            "sl": "num",
            "sno": "num",                        
            "sh/_smt": "salut",
            "sh/smt": "salut",
            "sh_/_smt": "salut",
            "sh": "salut",
            "": "salut",            
            "name_of_officers": "name",
            "name": "name",
            "father_name": "father_name",
            "father’s_name": "father_name",            
            "fnam": "father_name",
            "date_of_birth": "dob",
            "date_of_brith": "dob",            
            "dob": "dob",
            "home_distt": "home_district",
            "home_district": "home_district",
            "home-distt": "home_district",
            "hdst": "home_district",
            "present_posting": "post_stub",
            "ppst1": "post_stub",
            "place": "loca",
            "ppst2": "loca",
            "place_/_unit": "loca",
            "place/_units": "loca",
            "palce": "loca",
            "date_of_posting": "posting_date",
            "date_of_order": "posting_date",
            "dt_of_posting": "posting_date",
            "dop": "posting_date",
            "caste": "caste",

        }
    },
)
class InferHeaders:
    def __init__(self, conf_dir, conf_stub, pre_edit, header_dict):
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub
        self.pre_edit = pre_edit
        self.header_dict = header_dict
        
        self.lgr = logging.getLogger(f'docint.pipeline.{self.conf_stub}')
        self.lgr.setLevel(logging.DEBUG)
        
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)

    def __call__(self, doc):
        self.lgr.info(f'Processing {doc.pdf_name}')
        try:
            header_row = doc.pages[0].tables[0].header_rows[0]
            cells = header_row.cells
        except:
            self.lgr.info(f'\t{doc.pdf_name} Empty Header Row')
            assert False
            cells = []

        header_info = []
        for cell in cells:
            cell_text = cell.raw_text()
            header_text = cell_text.lower().replace('.','').replace(' ', '_').replace(',','').replace("'","")
            if header_text not in self.header_dict:
                self.lgr.info(f'\tNot Found: {doc.pdf_name} {cell_text}->{header_text}')
                continue
            header_info.append(self.header_dict[header_text])
        doc.header_info = header_info
        return doc


"""

@Vision.factory(
    "pdforder_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "buildorder",
        "pre_edit": True,
    },
)
class PDFOrderBuilder:
    def __init__(self, conf_dir, conf_stub, pre_edit):
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub
        self.pre_edit = pre_edit
        

        self.lgr = logging.getLogger(f'docint.pipeline.{self.conf_stub}')
        self.lgr.setLevel(logging.DEBUG)
        self.lgr.addHandler(logging.StreamHandler())


    def build_detail(self, row, header_row, detail_idx):
        pass
        
"""
