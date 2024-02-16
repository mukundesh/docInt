import logging  # noqa
import string
from collections import Counter
from typing import List

from pydantic import BaseModel

from docint.org_meta import OrgMeta
from docint.pdfwrapper import open as pdf_open
from docint.unicode_utils import get_script
from docint.vision import Vision


def is_text(doc, doc_path):
    pdf = pdf_open(doc_path)
    return all(len(p.images) == 0 for p in pdf.pages)


def is_multi_order(doc, page_languages):
    def text_match(w_text, text):
        if w_text.lower() == text or text in w_text.lower():
            print("TRUE", w_text, text)
            return True
        else:
            print("FALSE", w_text, text)
            return False

    def word_match(word, texts, x_range, y_range):
        texts = texts if isinstance(texts, list) else [texts]
        for text in texts:
            if (
                text_match(word.text, text)
                and word.box.in_xrange(x_range)
                and word.box.in_yrange(y_range)
            ):
                return True
        return False

    o_x_range, o_y_range = (0.35, 0.65), (0.05, 0.35)
    c_x_range, c_y_range = (0.0, 0.4), (0.0, 1.0)

    o_pages, c_pages = [], []
    for page, lang in zip(doc.pages, page_languages):
        o = (
            ["आदेश", "आज्ञा", "आंज्ञा", "संशोधन"]
            if lang.lower() == "devanagari"
            else ["order", "notification"]
        )
        c = (
            ["प्रतिलिपि", "प्रतिलपि", "प्रतिलिपी"]
            if lang.lower() == "devanagari"
            else ["copies", "copy"]
        )

        o_words = [w for w in page.words if word_match(w, o, o_x_range, o_y_range)]
        c_words = [w for w in page.words if word_match(w, c, c_x_range, c_y_range)]

        o_pages.append(1 if o_words else 0)
        c_pages.append(1 if c_words else 0)
        print(f'\tPage[{page.page_idx}] Found o: {",".join(str(w.word_idx) for w in o_words)}')
        print(f'\tPage[{page.page_idx}] Found c: {",".join(str(w.word_idx) for w in c_words)}')

    if sum(o_pages) > 1 and sum(c_pages) > 1:
        print(f"{doc.pdf_name}: multi_order: o_count: {sum(o_pages)} c_count: {sum(c_pages)}")
        return True
    else:
        print(f"{doc.pdf_name}: single_order: o_count: {sum(o_pages)} c_count: {sum(c_pages)}")
        return False


def get_language(doc):
    languages = []
    for page in doc.pages:
        counter = Counter(get_script(c) for w in page.words for c in w.text)
        languages.append(max(counter, key=counter.get, default="Basic Latin"))
    language = languages[0] if len(set(languages)) == 1 else "mixed"
    return language, languages


CadreDict = {
    "Constables": "Constable",
    "Inspectors and Company Commanders": "Insp/CC",
    "Head Constables": "HeadConst",
    "Assistant Sub Inspectors": "ASI",
    "R.P.S": "RPS",
    "Sub Inspectors and Platoon Commanders": "SI/PC",
    "I.P.S.": "IPS",
    "Ministerial Staff": "MiniStaff",
}


@Vision.factory(
    "org_meta_writer",
    default_config={
        "stub": "orgmetawriter",
    },
)
class OrgMetaWriter:
    def __init__(self, stub):
        self.stub = stub

    def split_path(self, doc_path):
        ws_pos = doc_path.parts.index("websites")
        stubs = doc_path.parts[ws_pos + 1 :]
        assert len(stubs) > 1
        return stubs[0], stubs[1:-1]

    def get_website_cadre_order_type(self, doc_path):
        website, website_path = self.split_path(doc_path)
        cadre = ""

        if website == "dop.rajasthan.gov.in":
            cadre = "IPS"
            order_type = "transfer/posting" if website_path[0] == "transfer" else website_path[0]
            return website, cadre, order_type
        elif website == "www.police.rajasthan.gov.in":
            if website_path[0] == "roster":
                return website, cadre, "roster"
            else:
                order_type = "transfer/posting"
                cadre = CadreDict[website_path[1]]
                return website, cadre, order_type

    def __call__(self, doc):
        doc.add_extra_field("org_meta", ("obj", "docint.org_meta", "OrgMeta"))
        # doc.add_extra_field("org_meta", ("noparse", '', ''))

        doc_path = doc.pdf_path.resolve()
        website, cadre, order_type = self.get_website_cadre_order_type(doc_path)

        language, languages = get_language(doc)

        # multi_order = is_multi_order(doc, languages)
        doc.org_meta = OrgMeta(
            is_text=is_text(doc, doc_path),
            language=language,
            page_languages=languages,
            cadre=cadre,
            order_type=order_type,
            website=website,
            file_name=doc_path.name,
        )
        # is_multi_order=multi_order)
        return doc
