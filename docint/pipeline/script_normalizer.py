import logging
import string
import sys
from pathlib import Path

import yaml

from ..data_error import DataError
from ..unicode_utils import get_script, scripts
from ..vision import Vision

# TODO
# 1. In Englisth lot of times a single character needs to be replaced è -> e
# 2. What if there is a punctuation 'fóx.' -> 'fox.'
# 3. text examples for other languages as well.


class MismatchedScriptError(DataError):
    text: str

    @classmethod
    def build(cls, doc, text, path):
        msg = f"MismatchedScriptError {path}: {text}"
        return MismatchedScriptError(msg=msg, path=path, text=text, doc=doc)


@Vision.factory(
    "script_normalizer",
    default_config={
        "script": "ascii",
        "script_mapping": "unicode.yml",
        "conf_stub": "script_normalizer",
    },
)
class ScriptNormalizer:
    def __init__(self, script, script_mapping, conf_stub):
        self.script = script
        self.conf_stub = conf_stub
        if script not in scripts:
            raise ValueError("Unknown script: {script}")

        if isinstance(script_mapping, dict):
            self.script_mapping = script_mapping
        else:
            yaml_str = Path(script_mapping).read_text()
            self.script_mapping = yaml.load(yaml_str, Loader=yaml.FullLoader)

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
        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def is_script(self, text):
        if self.script == "ascii":
            return text.isascii()

        script_found = None
        for ch in text:
            if ch in string.punctuation:
                continue

            ch_script = get_script(ch)
            if script_found and ch_script == script_found:
                continue
            elif not script_found:
                script_found = ch_script
            else:
                return False
        return True

    def __call__(self, doc):
        print(f"script_normalizer: {doc.pdf_name}")

        # TODO allow replacement of single character as well
        errors = []
        for word in (w for p in doc.pages for w in p.words):
            if not self.is_script(word.text):
                script_text = self.script_mapping.get(word.text, None)
                if script_text is None:
                    errors.append(MismatchedScriptError.build(doc, word.text, word.path))
                else:
                    word.replaceStr("<all>", script_text)

        print(f"== Errors Found: {len(errors)}")
        return doc
