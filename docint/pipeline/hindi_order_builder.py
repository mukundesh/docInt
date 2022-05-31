from typing import List
import logging
import sys
from pathlib import Path
import unicodedata
import re

from more_itertools import first, flatten
from polyleven import levenshtein

from ..vision import Vision
from ..extracts.orgpedia import Officer, OrderDetail, Order
from ..util import read_config_from_disk,load_config, find_date
from ..region import DataError
from ..word import Word
from ..span import Span
from . import PostParser


class BadCharsInNameError(DataError):
    pass

class IncorrectNameError(DataError):
    sub_str: str
    full_name: str
    pass

class UntranslatableTextsInPostError(DataError):
    texts: List[str] = []


PassthroughStr   = '.,()-/123456789:'
PasssthroughList = [ '11', '10', '12', '13', '14', '5th', '4th', '2nd', '7th', '10th', '3rd', '1st', '2 nd', 'SSW', 'th']
DotStr = '०0o..'            

@Vision.factory(
    "hindi_order_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "hindi_order_builder",
        "names_file": "names.yml",
        "has_relative_name": True,
        "name_split_strs": ["/"],
        "posts_file": "posts.yml",
        "cadre": "R.P.S.",
    },
)
class HindiOrderBuilder:
    def __init__(self, conf_dir, conf_stub, names_file, has_relative_name, name_split_strs, posts_file, cadre):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = conf_stub
        self.names_file = self.conf_dir / names_file
        self.has_relative_name = has_relative_name
        self.name_split_strs = name_split_strs
        self.posts_file = self.conf_dir / posts_file
        self.cadre = cadre

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
        self.post_leven_cache = {}

        self.post_parser = self.init_post_parser()

        self.lgr = logging.getLogger(f"docint.pipeline.{self.conf_stub}")
        self.lgr.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)
        self.file_handler = None

        self.fixes_dict = {}

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
        hi_name = hi_text.strip("()|।-:, 0123456789.$I[").replace("0", ".").replace('०', '.').replace('o', '.').replace(',', '.').replace('-', ' ')
        return hi_name

    def test_hi_name(self, hi_name, path, name_words):
        allowed_chars = '.|('
        uname = unicodedata.name
        hi_name = hi_name.replace(" ", "").replace("\n", "")
        if not all([uname(c).startswith("DEVANAGARI") for c in hi_name]):
            all_name_split_strs = ''.join(self.name_split_strs)
            bad = [c for c in hi_name if not uname(c).startswith("DEVANAGARI")]
            bad = [c for c in bad if c not in all_name_split_strs]
            bad = [c for c in bad if c not in allowed_chars]            
            if bad:
                bad_msgs = []
                for bad_char in bad:
                    bad_word = first([w for w in name_words if bad_char in w.text])
                    bad_msgs.append(f'{bad_char}< >{bad_word.text}[{bad_word.word_idx}]')
                msg = f'Has these bad chars: >{"< >".join(bad_msgs)}< in >{hi_name}<'
                return [BadCharsInNameError(path=path, msg=msg)]
        return []

    def get_salut(self, name, merged_saluts=True):
        short = "mr-mrs-dr-smt-shrimati-shri-sh-ms-श्रीमती-श्री-सुश्री-डॉ"

        print(f'SALUT >{name}<')

        saluts = []
        for s in short.split("-"):
            p = f"{s} -{s}. -({s}) -({s}.) -({s}.)-{s}."
            saluts.extend(p.split("-"))

        found_salut = first([s for s in saluts if name.lower().startswith(s)], "")

        if merged_saluts and (not found_salut):
            print('Merged Saluts Found')
            found_salut = "श्री" if name.startswith("श्री") else found_salut

        result = name[:len(found_salut)]
        return result

    def split_hi_name(self, hi_text):
        def has_name_split_str(hi_text):
            return any(nss for nss in self.name_split_strs if nss in hi_text)

        def split_on_name_split_str(hi_text):
            for nss in self.name_split_strs:
                if nss in hi_text:
                    return hi_text.split(nss, 1)
            return hi_text, ''

        hi_full, hi_relative = hi_text.strip(), ''
        
        if self.has_relative_name and has_name_split_str(hi_text):
            hi_full, hi_relative = split_on_name_split_str(hi_text)
            hi_full, hi_relative = hi_full.strip(), hi_relative.strip()

        hi_salut = self.get_salut(hi_full).strip()
        hi_name = hi_full[len(hi_salut):].strip()
        return hi_salut, hi_name, hi_relative

    def translate_name(self, hi_salut, hi_name, path):
        def transliterate_name(name_word):
            allowed_chars = '|/।(॥'
            if name_word == '.':
                return name_word
            elif name_word in allowed_chars:
                return ''
            else:
                msg = f'Missing >{name_word}< in >{hi_name}<'
                print(f'= Officer Error: {msg} {path}')
                errors.append(IncorrectNameError(path=path, msg=msg, sub_str=name_word, full_name=hi_name))
                return ''

        salut = self.salut_dict[hi_salut.strip(' .')]
        
        name_words, errors = [], []
        hi_name = hi_name.strip('. ')
        for hi_word in hi_name.split():
            name_word = self.names_dict.get(hi_word, None)
            if name_word:
                name_words.append(hi_word)
            else:
                name_words.append(transliterate_name(hi_word))
        return salut, ' '.join(name_words), errors

    def translate_name2(self, hi_salut, hi_name, path):
        def transliterate_name(name_word):
            allowed_chars = '|/।(॥'
            if name_word == '.':
                return name_word
            elif name_word in allowed_chars:
                return ''
            else:
                msg = f'Missing >{name_word}< in >{hi_name}<'
                print(f'= Officer Error: {msg} {path}')
                errors.append(IncorrectNameError(path=path, msg=msg, sub_str=name_word, full_name=hi_name))
                return ''

        if path == 'pa0.ta0.ro10.ce1':
            print('Found It')
            

        salut = self.salut_dict[hi_salut.strip(' .')]
        name_words, errors = [], []
        hi_name = hi_result = hi_name.strip('. ')
        for hi_word in re.split('[ .]+', hi_name):
            name_word = self.names_dict.get(hi_word, None)
            if name_word:
                hi_result = hi_result.replace(hi_word, name_word, 1)
            else:
                hi_trans = transliterate_name(hi_word)
                hi_result = hi_result.replace(hi_word, hi_trans, 1)

        print(f'Name: {path} {hi_salut}->{salut} {hi_name}->{hi_result}')
        return salut, hi_result, errors

    def get_officer(self, officer_cell, path):
        hi_text = officer_cell.arranged_text()

        # clean the text befor translation
        hi_text = self.fix_hi_name(hi_text)
        char_errors = self.test_hi_name(hi_text, path, officer_cell.words)
        if char_errors:
            print("= Officer Char Errors")            
            print('\n'.join(str(e) for e in char_errors))
            return (None, char_errors)
        
        # split the name in salut, name and relative_name
        hi_salut, hi_name, hi_relative = self.split_hi_name(hi_text)

        # translate salut, name and relative_name
        salut, name, name_errors = self.translate_name2(hi_salut, hi_name, path)
        relative_name, rel_errors = '', []        
        if hi_relative:
            _, relative_name, rel_errors = self.translate_name2('', hi_relative, path)
        
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
            cadre=self.cadre,
        )
        if name_errors:
            print("= Officer Name Errors")
            print('\n'.join(str(e) for e in char_errors))

        officer.errors = char_errors + name_errors + rel_errors
        return officer, officer.errors

    def find_post_leven_match(self, hi_text, cutoff=1):
        if hi_text in self.post_leven_cache:
            return self.post_leven_cache[hi_text]
        
        for hi_word, en_word in self.post_dict.items():
            if levenshtein(hi_word, hi_text, cutoff) <= cutoff:
                self.post_leven_cache[hi_text] = en_word
                print(f'>{hi_text}< Matches >{hi_word}<')
                return en_word
        return None

    def translate_post(self, hi_post):
        def translate(hi_text):
            en_words, un_words = ([], [])
            for hi_word in hi_text.split():
                hi_word = hi_word.strip(',।();॥"/\'')
                
                if (hi_word in PasssthroughList) or (hi_word in PassthroughStr):
                    en_words.append(hi_word)
                    continue
                # if hi_word in DotStr:
                #     en_words.append('.')
                #     print(f"FIXME PLEASE {hi_word}")
                #     continue
                    
                en_word = self.post_dict.get(hi_word, '')
                if en_word:
                    en_words.append(en_word)
                    continue
                
                hi_word_strip =  hi_word.strip(').')                
                en_word = self.post_dict.get(hi_word_strip, '')
                if en_word:
                    en_words.append(hi_word.replace(hi_word_strip, en_word))
                    continue

                en_word = self.find_post_leven_match(hi_word_strip)
                if en_word:
                    en_words.append(hi_word.replace(hi_word_strip, en_word))                
                else:
                    un_words.append(hi_word)
                    
            return en_words, un_words
        
        orig_hi_post = hi_post
        matched_span_stubs = []
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
        hi_text = hi_text.replace('०','.').replace('0', '.').replace('o', '.')

        # if path == "pa0.ta0.or0.ce3":
        #     #b /Users/mukund/Software/docInt/docint/pipeline/hindi_order_builder.py:247
        #     print('Found It') 

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

        post.errors = post_errors
        return post, post_errors


    def build_detail(self, row, path, detail_idx):
        officer_cell = row.cells[1] if len(row.cells) > 1 else None
        officer, officer_errors = self.get_officer(officer_cell, f"{path}.ce1")

        fr_post_cell = row.cells[2] if len(row.cells) > 2 else None
        to_post_cell = row.cells[3] if len(row.cells) > 3 else None

        fr_post, fr_post_errors = self.get_post(fr_post_cell, f"{path}.ce2")
        to_post, to_post_errors = self.get_post(to_post_cell, f"{path}.ce3")

        if not officer:
            return None, officer_errors + fr_post_errors + to_post_errors

        relinquishes = [] if fr_post_errors else [fr_post]
        assumes = [] if to_post_errors else [to_post]

        d = OrderDetail(
            words=row.words,
            word_line=[row.words],
            officer=officer,
            relinquishes=relinquishes,
            assumes=assumes,
            detail_idx=detail_idx,
        )
        errors = officer_errors + fr_post_errors + to_post_errors
        return d, errors


    def write_fixes(self, doc, errors):
        name_errors = [ e for e in errors if isinstance(e, IncorrectNameError)]

        for name_error in name_errors:
            row = [name_error.path, name_error.sub_str, name_error.full_name]
            cell = doc.get_region(name_error.path)
            cell_words = cell.arranged_words(cell.words)
            sub_idx = first((w.word_idx for w in cell_words if name_error.sub_str == w.text), -1)
                
            cell_word_str = '|'.join(f'{w.text}-{w.word_idx}' for w in cell_words)
            cell_img_str = cell.page.get_base64_image(cell.shape)
            row += [ str(sub_idx), cell_word_str, cell_img_str ]
            self.fixes_dict.setdefault(doc.pdf_name, []).append(row)

    def write_fixes_read_oldyml(self, doc, errors):
        def abbr_path(doc_path):
            abbr_path_fields = []
            for path_field in doc_path.split('.'):
                field = path_field.strip('0123456789')
                idx = path_field[len(field):]
                abbr_field = field[:2] if field != 'bodyRow' else 'ro'
                abbr_path_fields.append(f'{abbr_field}{idx}')
            return '.'.join(abbr_path_fields)

        def update_abbr_path(fix):
            fix['_abbrPath'] = abbr_path(fix['_docPath'])
            return fix

        def get_edits(fix):
            path = fix['_abbrPath']
            cell = doc.get_region(path)
            cell_text = cell.arranged_text()
            fix_text = fix.get('_devaStr', fix.get('_devStr', ''))

            if cell_text != fix_text:
                print(f"Fix Failure: mismatch {path} {cell_text} {fix_text}")

            edits = []
            for query in fix['queries']:
                assert first(query.keys()) == 'replaceStr'
                old, new = query['replaceStr']['old'], query['replaceStr']['new']
                if  old not in cell_text:
                    print(f'Fix Failure: {path} {old} not found in {cell_text}')
                    continue
                print(f'** Fix: >{cell_text}< old:{old} new:{new}')
                if 'IGNORE' == new:
                    edits.append(f"  - replaceStr {path} '{old}' '<empty>'")
                else:
                    edits.append(f"  - replaceStr {path} '{old}' '{new}'")
            print(f'Fix: Created edits: {path} {len(edits)}')
            return edits
                    
        fixes_file_path = self.conf_dir / f'{doc.pdf_name}.order_builder.yml'
        curr_fixes_str = fixes_file_path.read_text() if fixes_file_path.exists() else ''
        
        if 'edits:\n  - ' in curr_fixes_str:
            return []
        
        old_fixes_dir = Path('/Users/mukund/orgpedia/rajapoli/pipeline/R.P.S/image/annDoc_/conf')
        old_fixes_file = old_fixes_dir / f'fix.{doc.pdf_name}.yml'
        yml_dict = read_config_from_disk(old_fixes_file)

        error_paths = set(e.path for e in errors)        

        fixes = yml_dict.values()
        fixes = [ update_abbr_path(f) for f in fixes]
        fixes = [ f for f in fixes if f['_abbrPath'] in error_paths ]
        edits = list(flatten(get_edits(f) for f in fixes))

        if edits:
            fixes_lines = [curr_fixes_str] + ['edits:'] + edits
            fixes_file_path.write_text('\n'.join(fixes_lines))
        return edits

    def get_order_date(self, doc, word_path):
        if not word_path:
            return None
        
        words = doc.get_words(word_path)
        text = ' '.join(w.text for w in words)
        date, err = find_date(text)
        if err:
            print(f'OrderDateError: {doc.pdf_name} {err} >{text}<')
            
        print(f'OrderDate: {doc.pdf_name} {date} >{text}<')        
        return date

    def iter_rows(self, doc):
        for (page_idx, page) in enumerate(doc.pages):
            for (table_idx, table) in enumerate(page.tables):
                for (row_idx, row) in enumerate(table.body_rows):
                    yield page_idx, table_idx, row_idx, row

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"hindi_order_builder: {doc.pdf_name}")

        doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)

        old_name_split_strs = self.name_split_strs
        self.name_split_strs = doc_config.get('name_split_strs', self.name_split_strs)

        edits = doc_config.get("edits", [])
        if edits:
            print(f'Edited document: {doc.pdf_name}')
            doc.edit(edits)

        order_date = self.get_order_date(doc, doc_config.get("order_date", ""))
        #order_number = self.get_order_number(doc, doc_config.get("order_date", ""))
                                         
        doc.add_extra_field("order_details", ("list", __name__, "OrderDetails"))
        doc.add_extra_field("order", ("obj", __name__, "Order"))

        details, errors, detail_idx = [], [], 0
        
        for page_idx, table_idx, row_idx, row in self.iter_rows(doc):
            path = f"pa{page_idx}.ta{table_idx}.ro{row_idx}"

            detail, d_errors = self.build_detail(row, path, detail_idx)
            if detail:
                detail.errors = d_errors
            details.append(detail)
            errors.extend(d_errors)
            detail_idx += 1

        doc.order = Order.build(doc.pdf_name, order_date, doc.pdffile_path, details)
        doc.order.category = 'transfer'
        
        self.lgr.info(f'=={doc.pdf_name}.hindi_order_builder {len(details)} {DataError.error_counts(errors)}')            
        [self.lgr.info(str(e)) for e in errors]

        self.write_fixes(doc, errors)

        self.name_split_strs = old_name_split_strs
        self.remove_log_handler(doc)
        return doc


    def __del__(self):
        def get_html_row(row):
            row[-1] = f'<img src="{row[-1]}">'
            return '<tr><td>' + '</td><td>'.join(row) + '</td></tr>'

        def get_html_rows(pdf_name, rows):
            html_hdr = f'<tr><td colspan="{len(rows[0])}" style="text-align:center;">'
            html =  html_hdr + pdf_name + '</td></tr>'
            html += '\n'.join(get_html_row(r) for r in rows)
            return html

        def get_yml_row(row):
            path, sub_str, word_str = row[0], row[1], row[-2]
            yml = f'  # {path} >{sub_str}< {row[-2]}\n'
            page_path = path.split('.')[0]
            word_idx = row[-3]
            yml += f'  - replaceStr {page_path}.wo{word_idx} <all> {row[1]}\n'
            return yml

        def get_yml_rows(pdf_name, rows):
            yml_str = f'#F conf/{pdf_name}.order_builder.yml\n'
            yml_str += f'edits:\n'
            yml_str += '\n'.join(get_yml_row(r) for r in rows)
            return yml_str + '\n'


        headers = 'Path-Sub Str-Full Name-SubIdx-Words-Image'.split('-')
        html_fixes_path = Path('output') / 'fixes.html'
        html_str = '<html>\n<body>\n<table border=1>\n'
        html_str += '<tr><th>' + '</th><th>'.join(headers) + '</th></tr>'
        html_str += '\n'.join(get_html_rows(k, v) for k, v in self.fixes_dict.items())
        html_str += '\n</table>'
        html_fixes_path.write_text(html_str, encoding="utf-8")

        yml_fixes_path = Path('output') / 'fixes.yml'
        yml_str = '\n'.join(get_yml_rows(k, v) for k, v in self.fixes_dict.items())
        yml_fixes_path.write_text(yml_str, encoding="utf-8")
        
        
        
        
