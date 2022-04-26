import logging
import sys
from pathlib import Path
from more_itertools import first
from enchant import request_pwl_dict
import tempfile


from ..vision import Vision


from ..extracts.orgpedia import Officer, OrderDetail, OfficerID

from ..util import find_date, load_config
from ..region import DataError, UnmatchedTextsError

#b /Users/mukund/Software/docInt/docint/pipeline/id_assigner.py:34

@Vision.factory(
    "id_assigner",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "id_assigner",
        "pre_edit": True,
        "cadre_file_dict": {},
    },
)
class IDAssigner:
    def __init__(self, conf_dir, conf_stub, pre_edit, cadre_file_dict):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = Path(conf_stub)
        self.pre_edit = pre_edit

        self.cadre_names_dict = {}
        self.cadre_names_dictionary = {}
        for cadre, cadre_file in cadre_file_dict.items():
            officers = OfficerID.from_disk(cadre_file)
            names_dict = {}
            for o in officers:
                names = [o.name] + [a["name"] for a in o.aliases]
                names_nows = set(n.replace(" ", "") for n in names)
                [names_dict.setdefault(n.lower(), o.officer_id) for n in names_nows]
            self.cadre_names_dict[cadre] = names_dict

            dictionary_file = self.conf_dir / f'{cadre}.dict'
            if not dictionary_file.exists():
                dictionary_file.write_text("\n".join(names_dict.keys()))

            self.cadre_names_dictionary[cadre] = request_pwl_dict(str(dictionary_file))


        self.lgr = logging.getLogger(__name__)
        self.lgr.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)
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

    def get_officer_id(self, officer):
        name = officer.name

        
        assert name.isascii()
        name.strip(" .-")
        name_nows = name.replace(" ", "").lower()

        if not name_nows:
            return None

        names_dict = self.cadre_names_dict[officer.cadre]
        officer_id = names_dict.get(name_nows, None)
        if not officer_id:
            names_dictionary = self.cadre_names_dictionary[officer.cadre]
            suggestion = first(names_dictionary.suggest(name_nows), None)
            officer_id = names_dict.get(suggestion, None)
        return officer_id

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"id_assigner: {doc.pdf_name}")

        for detail in doc.order_details:
            officer = detail.officer

            officer_id = self.get_officer_id(officer)
            if not officer_id:
                idxs = ', '.join(f'{w.path_abbr}->{w.text}<' for w in officer.words)
                self.lgr.info(f'NotFound: {doc.pdf_name} {officer.name}\t{idxs}')
                officer_id = ''
                
            officer.officer_id = officer_id


        self.remove_log_handler(doc)        
        return doc
    
            
