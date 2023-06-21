import json
import os
from pathlib import Path

from more_itertools import flatten

from ..util import get_full_path, get_model_path, is_repo_path
from ..vision import Vision

MarathiNums = "१२३४५६७८९०.() "


def is_number(cell):
    cell = cell.strip(".) ")
    return all(c in MarathiNums for c in cell)


EnglishNums = "1234567890.() "
MarthiEnglishNumDict = dict((m, e) for (m, e) in zip(MarathiNums, EnglishNums))


def trans_number(cell):
    return "".join(MarthiEnglishNumDict[c] for c in cell)


def get_row_texts(row):
    return [c.text_with_break() for c in row.cells]


BatchSize = 100


@Vision.factory(
    "doc_translator_a4b",
    depends=[
        "docker:python:3.7-slim",
        "apt:git",
        "git+https://github.com/orgpedia/indic_nlp_library-deva.git",
        "ctranslate2==3.9.0",
        "sentencepiece",
    ],
    default_config={
        "stub": "doctranslator_a4b",
        "model_dir": "/import/models",
        "model_name": "ai4bharat:IndicTrans2-en/ct2_int8_model",
        "translations_file": "doc_translations.json",
        "output_dir": "output",
        "write_output": False,
        "src_lang": "hindi",
        "tgt_lang": "",
    },
)
class DocTranslatorAI4Bharat:
    def __init__(
        self,
        stub,
        model_dir,
        model_name,
        translations_file,
        output_dir,
        write_output,
        src_lang,
        tgt_lang,
    ):
        self.conf_dir = Path("conf")
        self.stub = stub
        self.model_dir = Path(model_dir)
        self.model_name = model_name

        if is_repo_path(self.model_dir):
            self.model_dir = get_full_path(self.model_dir)
        else:
            self.model_dir = Path(self.model_dir)

        self.translations_file = self.conf_dir / translations_file
        self.indic2en_trans = self.load_translations()

        self.output_dir = Path(output_dir)
        self.write_output = write_output
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.model = None

    def load_model(self):
        from ..models.indictrans.engine import Model

        print(self.model_dir)
        trans_model_dir = get_model_path(self.model_name, self.model_dir)
        print(trans_model_dir)
        return Model(str(trans_model_dir), device="cpu")

    def load_translations(self):
        indic2en_trans = {}
        if self.translations_file.exists():
            json_list = json.loads(self.translations_file.read_text())
            for trans_dict in json_list:
                m, e = trans_dict["mr"], trans_dict["en"]
                indic2en_trans[m] = e
        return indic2en_trans

    def save_translations(self):
        save_trans = sorted(
            [{"mr": k, "en": v} for (k, v) in self.indic2en_trans.items()],
            key=lambda d: d["mr"],
        )
        self.translations_file.write_text(json.dumps(save_trans, indent=2, ensure_ascii=False))

    def para_translate(self, para_texts):
        para_texts = [p for p in para_texts if p not in self.indic2en_trans]
        para_trans = [
            self.model.translate_paragraph(p, self.src_lang, self.tgt_lang) for p in para_texts
        ]
        for (p, t) in zip(para_texts, para_trans):
            self.indic2en_trans[p] = t
        self.save_translations()

    def sentences_translate(self, sents):
        sents = [s for s in sents if s not in self.indic2en_trans]
        sents_trans = self.model.batch_translate(sents, self.src_lang, self.tgt_lang)
        for (s, t) in zip(sents, sents_trans):
            self.indic2en_trans[s] = t
        self.save_translations()

    def get_text_trans(self, text):
        return None if text.isascii() else self.indic2en_trans[text]

    def get_table_trans(self, table):
        table_trans = []
        rows_texts = [get_row_texts(row) for row in table.all_rows]
        for row_texts in rows_texts:
            table_trans.append(
                [trans_number(c) if is_number(c) else self.get_text_trans(c) for c in row_texts]
            )
        return table_trans

    def process_doc(self, doc):
        doc.add_extra_page_field("para_trans", ("noparse", "", ""))
        doc.add_extra_page_field("table_trans", ("noparse", "", ""))

        if self.model is None:
            self.model = self.load_model()

        para_texts, cell_texts = [], []
        for page in doc.pages:
            pts = [p.text_with_break().strip() for p in page.paras]
            para_texts += [pt for pt in pts if not pt.isascii()]

            for row in [r for t in page.tables for r in t.all_rows]:
                cell_texts += [
                    c for c in get_row_texts(row) if not c.isascii() and not is_number(c)
                ]

        print("Calculated para_texts, cell_texts")
        para_texts, cell_texts = set(para_texts), set(cell_texts)
        self.para_translate(para_texts)

        print("Translated para_texts")
        self.sentences_translate(cell_texts)
        print("Translated cell_texts")

        for page in doc.pages:
            page.para_trans = [self.get_text_trans(p.text_with_break().strip()) for p in page.paras]
            page.table_trans = [self.get_table_trans(t) for t in page.tables]

        if self.write_output:
            json_path = self.output_dir / f"{doc.pdf_name}.{self.stub}.json"

            def get_para_infos(page):
                para_infos = []
                for para_idx, (para, trans) in enumerate(zip(page.paras, page.para_trans)):
                    para_infos.append(
                        {
                            "page_idx": page.page_idx,
                            "para_idx": para_idx,
                            "mr": para.text_with_break().strip(),
                            "en": trans,
                        }
                    )
                return para_infos

            def get_table_infos(page):
                table_infos = []
                for table_idx, table in enumerate(page.tables):
                    row_trans = page.table_trans[table_idx]
                    for row_idx, (row, row_texts) in enumerate(zip(table.all_rows, row_trans)):
                        cell_texts = [
                            {"mr": c.text_with_break(), "en": ct} for (c, ct) in zip(row, row_texts)
                        ]
                        table_infos.append(
                            {
                                "page_idx": page.page_idx,
                                "table_idx": table_idx,
                                "row_idx": row_idx,
                                "cells": cell_texts,
                            }
                        )
                return table_infos

            para_infos = list(flatten(get_para_infos(pg) for pg in doc.pages))
            table_infos = list(flatten(get_table_infos(pg) for pg in doc.pages))
            json_path.write_text(
                json.dumps(
                    {"para_infos": para_infos, "table_infos": table_infos},
                    indent=2,
                    ensure_ascii=False,
                )
            )

        return doc

    def pipe(self, docs, **kwargs):
        def generator_fun(docs):
            for doc in docs:
                self.process_doc(doc)
                yield doc

        yield from generator_fun(docs)
