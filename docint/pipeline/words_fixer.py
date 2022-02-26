import logging
import string
from pathlib import Path
import re
import itertools as it

from enchant import request_pwl_dict
from enchant.utils import levenshtein


from transformers import AutoTokenizer, AutoModelForTokenClassification
from transformers import pipeline

from ..vision import Vision
from ..region import TextConfig
from ..util import load_config



# b ../docint/pipeline/sents_fixer.py:87


@Vision.factory(
    "words_fixer",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "wordfix",
        "pre_edit": True,
        "dict_file": "output/pwl_words.txt",
        "lv_dist_cutoff": 1,
        "ignore_paren_len": 7
    },
)
class WordsFixer:
    def __init__(self, conf_dir, conf_stub, pre_edit, dict_file, lv_dist_cutoff, ignore_paren_len):
        self.punct_tbl = str.maketrans(
            string.punctuation, " " * len(string.punctuation)
        )
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub
        self.pre_edit = pre_edit
        self.dict_file = Path(dict_file)
        self.lv_dist_cutoff = lv_dist_cutoff
        self.ignore_paren_len = ignore_paren_len
        self.ignore_parent_strs = ['harg', 'depart', 'defence', 'banking', 'indep',
                                   'state', 'indapendent', 'smt .', 'deptt', 'shrimati',
                                   'indap', 'indop']


        self.dictionary = request_pwl_dict(str(self.dict_file))
        
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler())

        # TODO PLEASE MOVE THIS TO OPTIONS
        tokenizer = AutoTokenizer.from_pretrained("/Users/mukund/Github/huggingface/bert-base-NER")
        model = AutoModelForTokenClassification.from_pretrained("/Users/mukund/Github/huggingface/bert-base-NER")
        self.nlp = pipeline("ner", model=model, tokenizer=tokenizer)    

        

    def _fix_text(self, text):
        text = text.strip()
        text = text.translate(self.punct_tbl).strip()
        return text

    def is_correctable(self, text):
        suggestions = self.dictionary.suggest(text)
        if not suggestions:
            return False

        top_suggestion = suggestions[0].lower()
        lv_dist = levenshtein(top_suggestion, text.lower())
        #print(f'\t{text}->{suggestions[0]} {lv_dist}')
        
        if lv_dist <= self.lv_dist_cutoff or \
           top_suggestion.startswith(text.lower()):
            return True
        else:
            return False

    def is_mergeable(self, text, next_word):
        if next_word is None:
            return False

        next_text = self._fix_text(next_word.text)
        if not next_text:
            return False

        merged_text = text + next_text
        if self.dictionary.check(merged_text):
            #self.logger.debug(f"MergeFound >{text}+{next_text}<")
            return True
        elif self.is_correctable(merged_text):
            #self.logger.debug(f"MergeCorrected {merged_text}")
            return True
        else:
            #print(f"Merge NotFound {merged_text}")
            return False

    def merge_words(self, list_item):
        merge_count = 0
        ignore_config = TextConfig(rm_labels=['ignore', 'person'], rm_nl=True)
        
        for word, next_word in list_item.iter_word_pairs(ignore_config):
            text = self._fix_text(word.text)
            
            if not word or not next_word or not text:
                continue

            if self.is_mergeable(text, next_word):
                list_item.merge_word(word, next_word)
                #word.merge_word(next_word)
                merge_count += 1
        return merge_count

    def correct_words(self, list_item):
        correct_count = 0
        ignore_config = TextConfig(rm_labels=['ignore', 'person'], rm_nl=True)
        
        for text, word in list_item.iter_word_text(ignore_config):
            text = self._fix_text(text)
            if not word or not text:
                continue

            if len(text) <= 2 or self.dictionary.check(text):
                continue

            if self.is_correctable(text):
                suggestions = self.dictionary.suggest(text)
                self.logger.debug(f"SpellCorrected {text} -> {suggestions[0]}")

                list_item.replace_word_text(word, '<all>', suggestions[0])
                #word.replaceStr("<all>", suggestions[0])
                correct_count += 1
            else:
                self.logger.debug(f"SpellNOTFOUND {text}")                                
                
        return correct_count

    def mark_names2(self, list_item):
        ignore_config = TextConfig(rm_labels['ignore'], rm_nl=True)
        line_text = list_item.line_text(ignore_config)

        ner_results = self.nlp(line_text)
        ner_results = [ r for  r in ner_results if r['entity'].endswith('-PER') ]
        officer_spans = [ Span(r['start'], r['end']) for r in ner_results ]

        officer_spans = Span.reduce(officer_spans, ' .,')
        list_item.add_spans(officer_spans, 'officer', ignore_config)
        
        

    def mark_names(self, list_item):
        def get_person_spans(ner_results, line_text):
            def is_mergeable(last_end, new_start):
                if last_end == new_start:
                    return True
                elif line_text[last_end:new_start].strip(' .') == '':
                    return True
                else:
                    return False
    
            def merge_spans(spans, ner_result):
                # first time, change spans
                if isinstance(spans, dict):
                    first_start, first_end = spans['start'], spans['end']
                    spans = [ (first_start, first_end) ]

                last_start, last_end = spans[-1]
                if is_mergeable(last_end, ner_result['start']):
                    spans[-1] = (last_start, ner_result['end'])
                else:
                    spans.append((ner_result['start'], ner_result['end']))
                return spans
    
            person_spans = [r for r in ner_results if r['entity'].endswith('-PER')]
            person_spans.sort(key=lambda r: r['start'])
            if not person_spans:
                return []
            elif len(person_spans) == 1:
                return [ (person_spans[0]['start'], person_spans[0]['end']) ]
            

            *_, final_spans = it.accumulate(person_spans, func=merge_spans)
            return final_spans
        
        correct_count = 0
        ignore_config = TextConfig(rm_labels=['ignore'], rm_nl=True)
        line_text = list_item.line_text(ignore_config)

        ner_results = self.nlp(line_text)
        #self.logger.debug(ner_results)

        per_names = [ r['word'] for r in ner_results if r['entity'].endswith('-PER') ]

        #self.logger.debug(', '.join(per_names))

        person_spans = get_person_spans(ner_results, line_text)

        for start, end in person_spans:
            start = min(start, 0) if start < 25 else start
            list_item.add_span(start, end, 'person', ignore_config)
            #self.logger.debug(f'PERSON {line_text[start:end]}')

    def mark_manual_words(self, list_item):
        if list_item.get_spans('person'):
            return 0

        ignore_config = TextConfig(rm_labels=['ignore'], rm_nl=True)
        line_text = list_item.line_text(ignore_config)
        pm_words = ('the prime minister', 'prime minister', 'p.m.')
        pm_word = [ w for w in pm_words if line_text.lower().startswith(w) ]
        if pm_word:
            pm_word = pm_word[0]
            start = line_text.lower().index(pm_word)
            end = start + len(pm_word)
            list_item.add_span(start, end, 'person', ignore_config)
            self.logger.debug(f'PERSON {line_text[start:end]}')
            return 1
        else:
            return 0
            
    def blank_paren_words(self, list_item):
        text_config = TextConfig(rm_nl=True)
        line_text = list_item.line_text(text_config)
        
        char_list = list(line_text)
        paren_count = 0
        for m in re.finditer(r'\((.*?)\)', line_text):
            mat_str = m.group(1).lower()
            if len(mat_str) < self.ignore_paren_len:
                continue
            elif any([sl in mat_str for sl in self.ignore_parent_strs]):
                continue
            else:
                s, e = m.span()
                self.logger.debug(f'BLANKPAREN: {m.group(0)} ->[{s}: {e}]')
                #list_item.blank_line_text_no_nl(s, e)
                list_item.add_span(s, e, 'ignore', text_config)
                paren_count += 1
        #end for
        return paren_count


    def fix_list(self, list_item):
        paren_count = self.blank_paren_words(list_item)

        name_count = self.mark_names(list_item)

        merge_count = self.merge_words(list_item)
        
        #self.logger.debug(f'B>{list_item.line_text_no_nl()}')

        #self.logger.debug(f'A>{list_item.line_text_no_nl()}')        
        
        correct_count = self.correct_words(list_item)

        manual_count = self.mark_manual_words(list_item)

        return merge_count, correct_count

    def __call__(self, doc):
        self.logger.info(f"word_fixer: {doc.pdf_name}")

        if self.pre_edit:
            doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)
            edits = doc_config.get("edits", [])
            if edits:
                print(f'Edited document: {doc.pdf_name}')
                doc.edit(edits)
        
        NL = "\n"
        for page in doc.pages:
            # access what to fix through path
            for list_item in page.list_items:
                self.logger.debug(f'B>{list_item.line_text().replace(NL, " ")}<')
                self.fix_list(list_item)
                self.logger.debug(list_item.str_spans())
                self.logger.debug(f'A>{list_item.line_text().replace(NL, " ")}<\n')                
        return doc




