import logging
import sys
from pathlib import Path
from itertools import groupby
from more_itertools import first
from enchant import request_pwl_dict
import tempfile
import datetime
from dateutil import parser
from polyleven import levenshtein


from ..vision import Vision


from ..extracts.orgpedia import Officer, OrderDetail, OfficerID
from ..extracts.orgpedia import OfficerIDNotFoundError

from ..util import find_date, load_config, read_config_from_disk
from ..region import DataError, UnmatchedTextsError

#b /Users/mukund/Software/docInt/docint/pipeline/id_assigner_fields.py:34

@Vision.factory(
    "id_assigner_fields",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "id_assigner",
        "pre_edit": True,
        "cadre_file_dict": {},
        "post_id_fields": [],
        "officer_match_fields": [],
    },
)
class IDAssignerMultipleFields:
    def __init__(self, conf_dir, conf_stub, pre_edit, cadre_file_dict, post_id_fields, officer_match_fields):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = Path(conf_stub)
        self.pre_edit = pre_edit
        self.post_id_fields = post_id_fields

        self.cadre_officers_dict = {}        
        self.cadre_names_dict = {}

        self.cadre_names_dict2 = {}


        for cadre, cadre_file in cadre_file_dict.items():
            print(f'{cadre}: {cadre_file}')
            officers = OfficerID.from_disk(cadre_file)
            officers_dict, names_dict, names2_dict = {}, {}, {}
            duplicate_names, duplicate_officer_ids = set(), set()
            for o in officers:
                if o.officer_id == 'RR19861046':
                    print('Found It')
                    
                officers_dict[o.officer_id] = o
                names = [o.name] + [a["name"] for a in o.aliases]
                names_nows = set(n.lower().replace(" ", "") for n in names)

                # Approach 1
                already_present = [ n for n in names_nows if n in names_dict ]
                if already_present:
                    duplicate_names.update(already_present)
                    duplicate_officer_ids.update(names_dict[n] for n in already_present)
                    duplicate_officer_ids.add(o.officer_id)
                else:
                    [names_dict.setdefault(n.lower(), o.officer_id) for n in names_nows]

                # Approach 2
                [ names2_dict.setdefault(n, []).append(o) for n in names_nows]

            name_ids = names_dict.items()
            names_dict = dict( (n, i) for n, i in name_ids if i not in duplicate_officer_ids)
            self.cadre_names_dict[cadre] = names_dict
            self.cadre_officers_dict[cadre] = officers_dict
            print(f'Duplicates: {cadre}: {len(duplicate_officer_ids)} {duplicate_names}')
            self.cadre_names_dict2[cadre] = names2_dict
            
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

    def get_post_id(self, post, path):
        post_id_fields = post.fields if not self.post_id_fields else self.post_id_fields

        field_ids = []
        for field in post_id_fields:
            field_path = getattr(post, f'{field}_hpath')
            field_ids.append(f'{field[0].upper()}:{">".join(field_path)}')
        return ",".join(field_ids), []

    def search_officer_id(self, officer, name_nows, cutoff=1):
        def inv_equal(d1, d2):
            return d1.year == d2.year and d1.month == d1.day and d1.day == d2.month
        
        def date_match(dob1, dob2):
            return dob1 == dob2 or inv_equal(dob1, dob2)
        
        dob, cadre = officer.birth_date, officer.cadre
        names_dict = self.cadre_names_dict[cadre]
        for name, officer_id in names_dict.items():
            dist = levenshtein(name_nows, name, cutoff)
            if dist <= cutoff:
                officer_dob = self.cadre_officers_dict[cadre][officer_id].birth_date                    
                if not date_match(dob, officer_dob):
                    #print(f'DATE MISMATCH: {dist} {name_nows} -> {name} {dob} {officer_dob}')
                    pass
                else:
                    #print(f'Match: {dist} {name_nows} -> {name} {dob} {officer_dob}')
                    return officer_id
        return None

    def search_officer_id2(self, officer, name_nows, cutoff):
        def inv_equal(d1, d2):
            return d1.year == d2.year and d1.month == d1.day and d1.day == d2.month
        
        def date_match(dob1, dob2):
            return dob1 == dob2 or inv_equal(dob1, dob2)

        def get_officer_id(mat_officers, dob):
            def details(o):
                return f'{o.name}-{o.birth_date}'
            mat_officers = [ o for o in mat_officers if o.birth_date.__eq__(dob) ]
            assert len(mat_officers) in (0, 1), f'{",".join(details(o) for o in mat_officers)}'
            if len(mat_officers) == 1:
                return mat_officers[0].officer_id

            
            mat_officers = [ o for o in mat_officers if inv_equal(o.birth_date, dob) ]
            assert len(mat_officers) in (0, 1), f'INV: {",".join(o.name for o in mat_officers)}'                        
            if len(mat_officers) == 1:
                return mat_officers[0].officer_id

            return None

        def get_nodate_officer_id():
            nd_names, nd_officer_ids = [],[]
            for o_name_nows, mat_officers in names_dict.items():
                if levenshtein(o_name_nows, name_nows) <= cutoff:
                    nd_names.append(o_name_nows)
                    nd_officer_ids.extend((o.officer_id for o in mat_officers))

            nd_officer_ids  = set(nd_officer_ids)
            if len(nd_officer_ids) == 1:
                self.lgr.info(f'Found-nodate: {name_nows} -> {nd_names[0]}')
                return list(nd_officer_ids)[0]
            
            elif len(nd_officer_ids) > 1:
                names = ", ".join(nd_names)
                self.lgr.info(f'\tUNMATCHED-nodate: {name_nows} -> [{len(nd_officer_ids)}]{names}]')
            else:
                self.lgr.info(f'\tUNMATCHED-nodate: {name_nows} -> no match')
            return None
        
        dob, cadre = officer.birth_date, officer.cadre
        names_dict = self.cadre_names_dict2[cadre]
        
        if dob is None:
            return get_nodate_officer_id()
        

        mat_officers = names_dict.get(name_nows, [])

        officer_id = get_officer_id(mat_officers, dob)
        if officer_id:
            self.lgr.info(f'Found: {officer.name} -> {officer_id}')
            return officer_id

        unmatched = []
        for o_name_nows, mat_officers in names_dict.items():
            if levenshtein(o_name_nows, name_nows) <= cutoff:
                officer_id = get_officer_id(mat_officers, dob)
                if officer_id:
                    self.lgr.info(f'Found-Sim: {officer.name} -> {officer_id} {o_name_nows}')                    
                    return officer_id
                else:
                    dobs = ', '.join(f'{o.birth_date}' for o in mat_officers)
                    self.lgr.info(f'\tUNMATCHED-sim: {officer.name}({dob}) -> {o_name_nows}({dobs})')
                    if len(mat_officers) == 1:
                        unmatched.append((mat_officers[0].officer_id, dobs, o_name_nows))
        if len(unmatched) == 1:
            officer_id, u_dob, u_name = unmatched[0]
            if levenshtein(f'{dob}', u_dob) == 1:
                self.lgr.info(f'Found-date: {officer.name} -> {officer_id} {u_name} ({dob} = {u_dob})')                                    
                return officer_id

        self.lgr.info(f'UNMATCHED: {officer.name}({dob})')
        return None
        

    def get_officer_id(self, doc, officer, path):
        def fix_name(name):
            assert name.isascii()
            name.strip(" .-")
            name_nows = name.replace(" ", "").lower()
            return name_nows
        
        name = officer.name
        name_nows = fix_name(name)
        if not name_nows:
            return None, []

        if name_nows == 'hawa singh':
            print('Found It')
            

        #officer_id = self.search_officer_id(officer, name_nows, cutoff=2)
        officer_id = self.search_officer_id2(officer, name_nows, cutoff=2)        
        
        errors = []
        if not officer_id:
            idxs = ', '.join(f'{w.path_abbr}->{w.text}<' for w in officer.words)            
            msg = f"{self.conf_stub} {doc.pdf_name} >{name}< {idxs}"
            errors.append(OfficerIDNotFoundError(path=path, msg=msg))
            
        return officer_id, errors

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"id_assigner: {doc.pdf_name}")

        errors = []
        for detail in doc.order.details:
            officer = detail.officer
            officer_id, officer_errors = self.get_officer_id(doc, officer, detail.path)
            officer.officer_id = officer_id if officer_id else officer.officer_id

            errors.extend(officer_errors)
            for post in detail.get_posts('all'):
                post_id, post_errors = self.get_post_id(post, detail.path)
                post.post_id = post_id if post_id else post.post_id
                errors.extend(post_errors)
                

        self.lgr.info(f"=={doc.pdf_name}.id_assigner {len(doc.order.details)} {DataError.error_counts(errors)}")
        [self.lgr.info(str(e)) for e in errors]        
        self.remove_log_handler(doc)        
        return doc
    
            