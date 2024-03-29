from collections import Counter
from typing import Any, List

from pydantic import BaseModel


class DataError(BaseModel):
    path: str
    msg: str
    name: str

    def __str__(self):
        # if self.doc:
        #     return f"{self.name}: {self.doc.pdf_name} {self.path} {self.msg}"
        # else:
        return f"{self.name}: {self.path} {self.msg}"

    @property
    def error_name(self):
        return type(self).__name__

    @classmethod
    def error_counts(cls, errors):
        ctr = Counter(e.error_name for e in errors)
        type_str = " ".join(f"{n}={ct}" for n, ct in ctr.most_common(None))
        return f"Errors={sum(ctr.values())} {type_str}"

    @classmethod
    def ignore_error(cls, error, ignore_dict):
        error_name = type(error).__name__
        return error.path in ignore_dict.get(error_name, [])


class UnmatchedTextsError(DataError):
    texts: List[str]

    @classmethod
    def build(cls, path, unmatched_texts, post_str="", word_idxs=[]):
        msg = f'{",".join(unmatched_texts)}|{", ".join(word_idxs)}|{post_str}'
        return UnmatchedTextsError(path=path, msg=msg, texts=unmatched_texts, name="UnmatchedTexts")
