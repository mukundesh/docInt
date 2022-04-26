from typing import List
import logging
import sys
from pathlib import Path
import unicodedata

from more_itertools import first

from ..vision import Vision
from ..extracts.orgpedia import Officer, OrderDetail
from ..util import read_config_from_disk
from ..region import DataError
from ..word import Word
from ..span import Span
from . import PostParser


class BadCharsInNameError(DataError):
    pass

class IncorrectNameError(DataError):
    pass

class UntranslatableTextsInPostError(DataError):
    texts: List[str] = []


PassthroughStr   = '.,()-/123456789:'
PasssthroughList = [ '11', '10', '12', '13', '14', '5th', '4th', '2nd', '7th', '10th', '3rd', '1st', '2 nd', 'SSW']
DotStr = '०0o..'            

@Vision.factory(
    "hindi_order_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "hindi_order_builder",
        "names_file": "names.yml",
        "has_relative_name": True,
        "name_split_str": "/",
        "posts_file": "posts.yml",
    },
)
class HindiOrderBuilder:
    def __init__(self, conf_dir, conf_stub, names_file, has_relative_name, name_split_str, posts_file):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = conf_stub
        self.names_file = self.conf_dir / names_file
        self.has_relative_name = has_relative_name
        self.name_split_str = name_split_str
        self.posts_file = self.conf_dir / posts_file        

        self.names_dict = read_config_from_disk(self.names_file)["hindi_names"]
        self.salut_dict = {
            "श्रीमती": "Smt",
            "श्री": "Shri",
            "सुश्री": "Miss",
            "डॉ": "Dr.",
            "":"",
        }

        post_yml_dict = read_config_from_disk(self.posts_file)
        self.post_stubs_dict = post_yml_dict['stubs_translation']
        self.post_dict = post_yml_dict['translation']
        self.post_dict.update(post_yml_dict['juri_translation'])

        self.post_parser = self.init_post_parser()

        self.lgr = logging.getLogger(f"docint.pipeline.{self.conf_stub}")
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

    def init_post_parser(self):
        hierarchy_files = {
            "dept": "dept.yml",
            "role": "role.yml",
            "juri": "juri.yml",
            "loca": "loca.yml",
            "stat": "stat.yml",                        
        }
        return PostParser(self.conf_dir, hierarchy_files, "post.noparse.short.yml", ["ignore"], "postparser")


    def fix_hi_name(self, hi_text):
        hi_name = hi_text.strip("()|।-:, 0123456789.$I").replace("0", ".")
        return hi_name

    def test_hi_name(self, hi_name, path):
        uname = unicodedata.name
        hi_name = hi_name.replace(" ", "").replace("\n", "")
        if not all([uname(c).startswith("DEVANAGARI") for c in hi_name]):
            bad = [c for c in hi_name if not uname(c).startswith("DEVANAGARI")]
            bad = [c for c in bad if c not in self.name_split_str]
            if bad:
                msg = f'Has these bad chars: >{"<>".join(bad)}<'
                return [BadCharsInNameError(path=path, msg=msg)]
        return []

    def get_salut(self, name, merged_saluts=True):
        short = "mr-mrs-dr-smt-shri-sh-ms-श्रीमती-श्री-सुश्री-डॉ"

        saluts = []
        for s in short.split("-"):
            p = f"{s} -{s}. -({s}) -({s}.) -({s}.)-{s}."
            saluts.extend(p.split("-"))

        found_salut = first([s for s in saluts if name.lower().startswith(s)], "")

        if merged_saluts and (not found_salut):
            found_salut = "श्री" if name.startswith("श्री") else found_salut

        result = name[:len(found_salut)]
        return result

    def split_hi_name(self, hi_text):
        hi_full, hi_relative = hi_text.strip(), ''
        if self.has_relative_name and self.name_split_str in hi_text:
            hi_full, hi_relative = hi_text.split(self.name_split_str, 1)
            hi_full, hi_relative = hi_full.strip(), hi_relative.strip()

        hi_salut = self.get_salut(hi_full).strip()
        hi_name = hi_full[len(hi_salut):].strip()
        return hi_salut, hi_name, hi_relative

    def translate_name(self, hi_salut, hi_name, path):
        def transliterate_name(name):
            msg = f'Missing >{name}<'
            print(f'= Officer Error: {msg} {path}')
            errors.append(IncorrectNameError(path=path, msg=msg))
            return ''

        salut = self.salut_dict[hi_salut]
        
        name_words, errors = [], []
        for hi_word in hi_name.strip('. ').split():
            name_word = self.names_dict.get(hi_word, None)
            if name_word:
                name_words.append(name_word)
            else:
                name_words.append(transliterate_name(hi_word))
        return salut, ' '.join(name_words), errors

    def get_officer(self, officer_cell, path):
        hi_text = officer_cell.raw_text()

        # clean the text befor translation
        hi_text = self.fix_hi_name(hi_text)
        char_errors = self.test_hi_name(hi_text, path)
        if char_errors:
            print("= Officer Char Errors")            
            print('\n'.join(str(e) for e in char_errors))
            return (None, char_errors)
        
        # split the name in salut, name and relative_name
        hi_salut, hi_name, hi_relative = self.split_hi_name(hi_text)

        # translate salut, name and relative_name
        salut, name, name_errors = self.translate_name(hi_salut, hi_name, path)
        relative_name, rel_errors = '', []        
        if hi_relative:
            _, relative_name, rel_errors = self.translate_name('', hi_relative, path)
        
        full_name = f"{salut} {name}"
        officer = Officer(
            words=officer_cell.words,
            word_line=[officer_cell.words],
            salut=salut,
            name=name,
            relative_name=relative_name,
            full_name=full_name,
            orig_lang="hi",
            orig_salut=hi_salut,
            orig_name=hi_name,
            orig_full_name=hi_text,
        )
        if name_errors:
            print("= Officer Name Errors")
            print('\n'.join(str(e) for e in char_errors))            
            
        return officer, char_errors + name_errors + rel_errors

    def translate_post(self, hi_post):
        def translate(hi_text):
            en_words, un_words = ([], [])
            for hi_word in hi_text.split():
                en_word = self.post_dict.get(hi_word, '')
                if en_word:
                    en_words.append(en_word)
                elif (hi_word in PasssthroughList) or (hi_word in PassthroughStr):
                    en_words.append(hi_word)
                elif hi_word in DotStr:
                    en_words.append('.')
                else:
                    un_words.append(hi_word)
            return en_words, un_words
        
        orig_hi_post = hi_post
        matched_span_stubs, un_words = [], []
        # replace stubs
        for (hi_stub, en_stub) in self.post_stubs_dict.items():
            if hi_stub in hi_post:
                stub_span = Span.find_first(hi_post, hi_stub)
                hi_post = Span.blank_text([stub_span], hi_post)
                matched_span_stubs.append((stub_span, en_stub))
                if hi_stub  in hi_post:
                    self.lgr.warning(f'Multiple matches of {hi_stub} in {orig_hi_post}')

        matched_spans = [tup[0] for tup in matched_span_stubs]

        untrans_texts = []
        un_texts, un_spans = Span.unmatched_texts_spans(matched_spans, hi_post)
        for un_text, un_span in zip(un_texts, un_spans):
            en_words, untrans_words = translate(un_text)
            if en_words:
                en_text = ' '.join(en_words)
                matched_span_stubs.append((un_span, en_text))
            untrans_texts.extend(untrans_words)
        matched_span_stubs.sort(key=lambda tup: tup[0].start)
        post_str = ' '.join(tup[1] for tup in matched_span_stubs)
        return post_str, untrans_texts
        

    def get_post(self, post_cell, path):
        #hi_text = post_cell.raw_text()
        hi_text = post_cell.arranged_text()
        hi_text = hi_text.replace('\n', ' ').replace('|','').strip('|। ()')

        if path == "p1.t0.r16.c2":
            #b /Users/mukund/Software/docInt/docint/pipeline/hindi_order_builder.py:246
            print('Found It')

        post_str, untrans_texts = self.translate_post(hi_text)
        if untrans_texts:
            print(f'hi:>{hi_text}< en:>UntranslatableTextsInPostError< {path}')            
            msg = f'Untranslatable texts: >{"<, >".join(untrans_texts)}< >{hi_text}<'
            trans_err = UntranslatableTextsInPostError(msg=msg, path=path, texts=untrans_texts)
            return None, [trans_err]

        print(f'hi:>{hi_text}< en:>{post_str}< {path}')
        post = self.post_parser.parse(post_cell.words, post_str, path)
        post_errors = self.post_parser.test(post, path)
        if post_errors:
            print("= Post Error")
            print("\n".join(str(e) for e in post_errors))
        return post, post_errors


    def build_detail(self, row, path, detail_idx):
        errors = []
        officer_cell = row.cells[1] if len(row.cells) > 1 else None
        officer, officer_errors = self.get_officer(officer_cell, f"{path}.c1")

        fr_post_cell = row.cells[2] if len(row.cells) > 2 else None
        to_post_cell = row.cells[3] if len(row.cells) > 3 else None

        fr_post, fr_post_errors = self.get_post(fr_post_cell, f"{path}.c2")
        to_post, to_post_errors = self.get_post(to_post_cell, f"{path}.c3")

        if not officer:
            return None, officer_errors + fr_post_errors + to_post_errors

        d = OrderDetail(
            words=row.words,
            word_line=[row.words],
            officer=officer,
            relinquishes=[], #
            assumes=[],#
            detail_idx=detail_idx,
        )
        return d, officer_errors + fr_post_errors + to_post_errors

    def iter_rows(self, doc):
        for (page_idx, page) in enumerate(doc.pages):
            for (table_idx, table) in enumerate(page.tables):
                for (row_idx, row) in enumerate(table.body_rows):
                    yield page_idx, table_idx, row_idx, row

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"hindi_order_builder: {doc.pdf_name}")
        doc.add_extra_field("order_details", ("list", __name__, "OrderDetails"))
        doc.add_extra_field("order", ("obj", __name__, "Order"))

        details, errors = [], []
        self.verb = "continues"  # self.get_verb(doc)

        for page_idx, table_idx, row_idx, row in self.iter_rows(doc):
            path = f"p{page_idx}.t{table_idx}.r{row_idx}"

            detail, d_errors = self.build_detail(row, path, row_idx)
            if detail:
                detail.errors = d_errors
            details.append(detail)
            errors.extend(d_errors)

        self.lgr.info(f'=={doc.pdf_name}.hindi_order_builder {len(details)} {DataError.error_counts(errors)}')            
        [self.lgr.info(str(e)) for e in errors]
        
        self.remove_log_handler(doc)
        return doc
