import logging
import string
from collections import Counter
from pathlib import Path

from ..vision import Vision


@Vision.factory(
    "wordfreq_writer",
    default_config={
        "doc_confdir": "conf",
        "pre_edit": True,
        "wordfreq_dir": "output",
        "min_count": 4,
    },
)
class WordfreqWriter:
    def __init__(self, doc_confdir, pre_edit, wordfreq_dir, min_count):
        self.punct_tbl = str.maketrans(string.punctuation, " " * len(string.punctuation))
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.wordfreq_dir = Path(wordfreq_dir)
        self.min_count = min_count

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(logging.StreamHandler())

    def fix_text(self, text):
        text = text.strip()
        text = text.translate(self.punct_tbl).strip()
        return text.lower()

    def __call__(self, doc):
        self.logger.info(f"wordfreq_writer: {doc.pdf_name}")
        counter = Counter()
        for page in doc.pages:
            for list_item in page.list_items:
                textList = []
                for w in list_item.words:
                    text = self.fix_text(w.text)
                    if text:
                        textList.extend(text.split())
                counter.update(textList)

        ord_texts = counter.most_common(None)
        ord_texts = [f"{t} {c}" for (t, c) in ord_texts if c >= self.min_count]
        wordfreq_file = self.wordfreq_dir / (doc.pdf_name + ".wordfreq.txt")
        wordfreq_file.write_text("\n".join(ord_texts))
        return doc
