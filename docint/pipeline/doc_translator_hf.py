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
        "git+https://github.com/orgpedia/indicTranslate.git",
    ],
    default_config={
        "stub": "doctranslator",
        "model_name": "ai4bharat:IndicTrans2-en/ct2_int8_model",
        "glossary_file": "glossary.yml",
        "src_lang": "hindi",
        "tgt_lang": "",
        "entities": ["paras", "table"],
    },
)
class DocTranslator:
    def __init__(
        self,
        stub,
        model_name,
        src_lang,
        tgt_lang,
        entities,
    ):
        from indicTranslate import Translator

        self.conf_dir = Path("conf")
        self.stub = stub
        self.translator = Translator(model_name, src_lang, tgt_lang)
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.entities = entities

    def get_table_trans(self, table, cell_trans_dict):
        t_table = []
        for row in table.rows:
            t_table.append([c if c.isascii() else cell_trans_dict[c] for c in get_row_texts(row)])
        return t_table

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

        para_texts, cell_texts = [], []
        for page in doc.pages:
            pts = [p.text_with_break().strip() for p in page.paras]
            para_texts += [pt for pt in pts if not pt.isascii()]

            for row in [r for t in page.tables for r in t.all_rows]:
                cell_texts += [c for c in get_row_texts(row) if not c.isascii()]

        para_trans = self.translator.translate_paragraphs(para_texts)
        cell_trans = self.translator.translate_sentences(cell_texts)

        para_trans_dict = {p: t for (p, t) in zip(para_texts, para_trans)}
        cell_trans_dict = {c: t for (c, t) in zip(cell_texts, cell_trans)}

        for page in doc.pages:
            para_texts = [p.text_with_break().strip() for p in page.paras]
            page.para_trans = [pt if pt.is_ascii() else para_trans_dict[pt] for pt in para_texts]
            page.table_trans = [self.get_table_trans(t, cell_trans_dict) for t in page.tables]

        all_para_tans = [pg.para_trans for pg in doc.pages]
        all_table_trans = [pg.table_trans for pg in doc.pages]
        trans_dict = {"all_para_tans": all_para_tans, "all_table_trans": all_table_trans}

        json_path.write_text(json.dumps(trans_dict))
        return doc

    def process_all(self, docs, **kwargs):
        def generator_fun(docs):
            for doc in docs:
                yield self(doc)

        yield from generator_fun(docs)
