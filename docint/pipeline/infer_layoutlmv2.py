import gc
import itertools
import logging
from itertools import chain, islice
from pathlib import Path

from ..region import Region
from ..vision import Vision
from .learn_layoutlmv2 import generate_dataset


def iob2label(label):
    return label[2:] if label else "other"


@Vision.factory(
    "infer_layoutlmv2",
    depends=[
        "transformers[torch]",
        "git+https://github.com/facebookresearch/detectron2.git",
        "seqeval",
        "datasets",
    ],
    default_config={
        "page_idx": 0,
        "batch_size": 10,
        "model_dir": "input/model",
        "proc_model_name": "microsoft/layoutlmv2-base-uncased",
        "infer_model_name": "orgpedia/cabsec-layoutlmv2",
    },
)
class InferLayoutLMv2:
    def __init__(
        self,
        page_idx,
        batch_size,
        model_dir,
        proc_model_name,
        infer_model_name,
    ):
        self.page_idx = page_idx
        self.batch_size = batch_size
        self.model_dir = Path(model_dir)
        self.proc_model_name = proc_model_name
        self.infer_model_name = infer_model_name

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(logging.StreamHandler())

    def eval(self, ptDataset):
        def grouper(iterable, n, fillvalue=None):
            "Collect data into fixed-length chunks or blocks"
            # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
            args = [iter(iterable)] * n
            return itertools.zip_longest(*args, fillvalue=fillvalue)

        self.logger.info(f"Evaluating model with batch_size: {self.batch_size}")

        infer_model_dir = self.model_dir / Path(self.infer_model_name).name

        import torch
        from torch.utils.data import DataLoader
        from tqdm.auto import tqdm
        from transformers import LayoutLMv2ForTokenClassification

        model = LayoutLMv2ForTokenClassification.from_pretrained(infer_model_dir)
        model.eval()
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        examples_loader = DataLoader(ptDataset, batch_size=self.batch_size)
        word_labels_list = []
        for batch in tqdm(examples_loader, desc="Evaluating"):

            with torch.no_grad():
                input_ids = batch["input_ids"].to(device)
                bbox = batch["bbox"].to(device)
                image = batch["image"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                token_type_ids = batch["token_type_ids"].to(device)

                # forward pass
                outputs = model(
                    input_ids=input_ids,
                    bbox=bbox,
                    image=image,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                )  # no labels

                # predictions
                labels = batch["labels"].squeeze().tolist()
                labels = [labels] if len(batch["input_ids"]) == 1 else labels
                predictions = outputs.logits.argmax(dim=2)

                print(f"predictions.shape: {predictions.shape}")
                print(f"len(labels): {len(labels)}")
                print(f"len(labels[0]): {len(labels[0])}")

                # Remove ignored index (special tokens)
                true_predictions = [
                    [model.config.id2label[p.item()] for (lb, p) in zip(label, prediction) if lb != -100]
                    for label, prediction in zip(labels, predictions)
                ]

            word_labels_list.extend(true_predictions)
        return word_labels_list

    def pipe(self, docs, **kwargs):
        def chunks(iterable, size=10):
            iterator = iter(iterable)
            for first in iterator:
                yield chain([first], islice(iterator, size - 1))

        self.logger.info("Entering infer_layoutlm.pipe")

        docs = list(docs)
        for chunk_idx, docs_chunk in enumerate(chunks(docs, self.batch_size * 5)):
            infer_pages = [d[self.page_idx] for d in docs_chunk]
            hf_dataset, _, _ = generate_dataset(infer_pages, self.model_dir, self.proc_model_name, has_labels=False)

            self.logger.info("Generated pytorch dataset")

            word_labels_list = self.eval(hf_dataset)

            assert len(infer_pages) == len(word_labels_list)

            for doc in docs_chunk:
                doc.add_extra_page_field("word_labels", ("dict", "docint.region", "Region"))

            for (word_labels, page) in zip(word_labels_list, infer_pages):
                print(f"{page.doc.pdf_name} words: {len(page.words)} labels: {len(word_labels)} -----------")
                label_word_dict = {}
                for (word_idx, label) in enumerate(word_labels[: len(page.words)]):
                    label_word_dict.setdefault(iob2label(label), []).append(page[word_idx])

                lw_iter = label_word_dict.items()
                page.word_labels = dict((l, Region.from_words(ws)) for (l, ws) in lw_iter)

                for label, region in page.word_labels.items():
                    print(f"{label}: {region.raw_text()}")
                print("")
            # end for
            del hf_dataset
            gc.collect()
        return docs
