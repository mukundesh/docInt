import json
import os
from pathlib import Path

from more_itertools import flatten

from ..util import get_full_path, get_model_path, is_readable_nonempty, is_repo_path
from ..vision import Vision


def get_row_texts(row):
    return [c.text_with_break() for c in row.cells]


BatchSize = 100


@Vision.factory(
    "doc_translator_hf",
    depends=[
        "docker:python:3.8-slim",
        "apt:git",
        "git+https://github.com/orgpedia/translateIndic.git",
    ],
    default_config={
        "stub": "doctranslator",
        "model_name": "default",
        "glossary_path": "conf/glossary.yml",
        "src_lang": "eng_Latn",
        "tgt_lang": "hin_Deva",
        "entities": ["paras", "table"],
    },
)
class DocTranslator:
    def __init__(
        self,
        stub,
        model_name,
        glossary_path,
        src_lang,
        tgt_lang,
        entities,
    ):
        from translateindic import Translator

        self.conf_dir = Path("conf")
        self.stub = stub
        self.glossary_path = Path(glossary_path)
        if self.glossary_path.exists():
            self.translator = Translator(
                model_name,
                src_lang,
                tgt_lang,
                glossary_path=self.glossary_path,
                enable_numeric=True,
            )
        else:
            self.translator = Translator(model_name, src_lang, tgt_lang, enable_numeric=True)
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.entities = entities

    def get_table_trans(self, table, cell_trans_dict):
        t_table = []
        for row in table.all_rows:
            # t_table.append([c if c.isascii() else cell_trans_dict[c] for c in get_row_texts(row)])
            t_table.append(
                [c if self.in_tgt_lang(c) else cell_trans_dict[c] for c in get_row_texts(row)]
            )
        return t_table

    def in_tgt_lang(self, s):
        if self.tgt_lang == "eng_Latn":
            return s.isascii()
        else:
            # Todo check and compare but leaving it for now
            return False

    def __call__(self, doc):
        doc.add_extra_page_field("para_trans", ("noparse", "", ""))
        doc.add_extra_page_field("table_trans", ("noparse", "", ""))

        json_path = Path("output") / f"{doc.pdf_name}.{self.stub}.json"

        if json_path.exists():
            jd = json.loads(json_path.read_text())

            zip_iter = zip(doc.pages, jd["all_para_trans"], jd["all_table_trans"])
            for page, page_para_trans, page_table_trans in zip_iter:
                page.para_trans = page_para_trans
                page.table_trans = page_table_trans
            return doc

        last_trans_page_idx = max([p.page_idx for p in doc.pages if getattr(p, "paras", [])], default=0)
        para_texts, cell_texts = [], []
        for page in doc.pages:
            if page.page_idx > last_trans_page_idx:
                break

            page_paras = page.paras if hasattr(page, "paras") else []
            pts = [p.text_with_break().strip() for p in page_paras]
            # para_texts += [pt for pt in pts if not pt.isascii()]
            para_texts += [pt for pt in pts if not self.in_tgt_lang(pt)]

            page_tables = page.tables if hasattr(page, "tables") else []
            for row in [r for t in page_tables for r in t.all_rows]:
                cell_texts += [c for c in get_row_texts(row) if not self.in_tgt_lang(c)]

        print(f"Paras: #{len(para_texts)} Sentences: #{len(cell_texts)}")

        cell_trans = self.translator.translate_sentences(cell_texts)
        print("Done translating sentences")

        para_trans = self.translator.translate_paragraphs(para_texts)
        print("Done translating paras")

        para_trans_dict = {p: t for (p, t) in zip(para_texts, para_trans)}
        cell_trans_dict = {c: t for (c, t) in zip(cell_texts, cell_trans)}

        for page in doc.pages:
            page_paras = page.paras if hasattr(page, "paras") else []
            para_texts = [p.text_with_break().strip() for p in page_paras]
            page.para_trans = [pt if pt.isascii() else para_trans_dict[pt] for pt in para_texts]

            if page.page_idx <= last_trans_page_idx:
                page_tables = page.tables if hasattr(page, "tables") else []
                page.table_trans = [self.get_table_trans(t, cell_trans_dict) for t in page_tables]
            else:
                page.table_trans = []

        all_para_trans = [pg.para_trans for pg in doc.pages]
        all_table_trans = [pg.table_trans for pg in doc.pages]
        trans_dict = {"all_para_trans": all_para_trans, "all_table_trans": all_table_trans}

        json_path.write_text(json.dumps(trans_dict))
        return doc

    def process_all(self, docs, **kwargs):
        def generator_fun(docs):
            for doc in docs:
                yield self(doc)

        yield from generator_fun(docs)
