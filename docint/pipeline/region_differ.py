import logging
import sys
from pathlib import Path
from pprint import pprint

from ..region import DataError
from ..vision import Vision

# b ../docint/pipeline/sents_fixer.py:87


class TextDiffError(DataError):
    pass


class ShapeDiffErrorr(DataError):
    pass


@Vision.factory(
    "region_differ",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "diff",
        "reference_dir": "output",
        "reference_ext": "list",
    },
)
class RegionDiffer:
    def __init__(self, conf_dir, conf_stub, reference_dir, reference_ext):
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub
        self.reference_dir = Path(reference_dir)
        self.reference_ext = reference_ext

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
        self.lgr.info(f"adding handler {log_path}")

        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def __call__(self, doc):
        import jsondiff

        self.add_log_handler(doc)
        self.lgr.info(f"region_differ: {doc.pdf_name}")

        ref_path = self.reference_dir / f"{doc.pdf_name}.{self.reference_ext}.json"
        if not ref_path.exists():
            self.lgr.info("Unable to find {ref_path} skipping")

        ref_doc = doc.from_disk(ref_path)
        ref_dict = ref_doc.dict()

        doc_dict = doc.dict()

        diffs = jsondiff.diff(ref_dict, doc_dict)
        pprint(diffs)
        print(f"{doc.pdf_name} diffs: {len(diffs)}")

        # self.lgr.info(f'=={doc.pdf_name}.region_differ {DataError.error_counts(errors)}')
        # [self.lgr.info(str(e)) for e in errors]

        self.remove_log_handler(doc)
        return doc
