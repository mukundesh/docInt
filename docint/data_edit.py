from pydantic import BaseModel


class DataEdit(BaseModel):
    msg: str

    def __str__(self):
        return self.msg


class MergeWordEdit(DataEdit):
    keep_word_path: str
    elim_word_path: str
    elim_word_text: str
    keep_word_text: str

    @classmethod
    def build(cls, keep_word, elim_word):
        w1, w2 = keep_word, elim_word
        t1, t2 = w1.text, w2.text
        msg = f"{t1}<->{t2}"
        return MergeWordEdit(
            keep_word_path=w1.path,
            elim_word_path=w2.path,
            keep_word_text=t1,
            elim_word_text=t2,
            msg=msg,
        )


class ReplaceTextEdit(DataEdit):
    word_path: str
    old_text: str
    new_text: str

    @classmethod
    def build(cls, word, old_text, new_text):
        old_wtext = word.text
        msg = f"{old_wtext}->{old_wtext.replace(old_text, new_text)}"
        return ReplaceTextEdit(word_path=word.path, old_text=old_text, new_text=new_text, msg=msg)
