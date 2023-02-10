import logging
from pathlib import Path

from more_itertools import pairwise

from ..region import Region
from ..util import load_config
from ..vision import Vision

MAX_IMAGE_HEIGHT = 1000

# TODO: 1. Model save options locally, huggingface cloud
# TODO: 2 Save the results and verify the model is correct


def get_wand_array(page_image):
    # TODO: Unable to use Wand to for doing imaging resizing as the processor is failing
    # with type mismatch error.
    # ValueError: Images must of type `PIL.Image.Image`, `np.ndarray` or `torch.Tensor`
    # (single example), `List[PIL.Image.Image]`, `List[np.ndarray]` or `List[torch.Tensor]`
    # (batch of examples), but is of type <class 'list'>
    #
    # This could also be a python 3.7 issue as this fails
    # print(isinstance(images, List[np.ndarray]))
    import numpy as np
    from wand.image import Image as WandImage

    image_path = Path(page_image.image_path)
    if not image_path.exists():
        image_path = Path(".img") / image_path.parent.name / Path(image_path.name)

    with WandImage(filename=image_path) as image:
        orig_w, orig_h = image.size
        h_scale = MAX_IMAGE_HEIGHT / orig_h
        new_w = int(orig_w * h_scale)
        image.resize(new_w, MAX_IMAGE_HEIGHT)
        ar = np.asarray(bytearray(image.make_blob()), dtype=np.int64)
    return ar


def check_datset(data_dict):
    num_examples = len(data_dict["id"])
    assert all(len(v) == num_examples for v in data_dict.values())

    zip_iter = zip(data_dict["texts"], data_dict["bboxes"], data_dict["ner_tags"])
    assert all(len(t) == len(b) == len(n) for (t, b, n) in zip_iter)

    max_val = MAX_IMAGE_HEIGHT
    for page_id, example in zip(data_dict["id"], data_dict["bboxes"]):
        for idx, box in enumerate(example):
            for coord_val in box:
                assert (
                    0 <= coord_val <= max_val
                ), f"incorrect coord_val: {coord_val} {page_id} word: {idx}"

    assert all(0 <= c <= max_val for e in data_dict["bboxes"] for b in e for c in b)
    assert all(len(b) == 4 for e in data_dict["bboxes"] for b in e)
    assert all(i.size[0] <= i.size[1] == max_val for i in data_dict["pil_images"])


def generate_dataset(learn_pages, model_dir, model_name, has_labels=True):
    class_labels = set()

    def get_ner_tags(page):
        ner_tags = ["O"] * len(page.words)
        if not has_labels:
            class_labels.update(ner_tags)
            return ner_tags

        lr_items = page.word_labels.items()
        label_region_iter = ((lab, r.words) for lab, rs in lr_items for r in rs)
        for (label, words) in label_region_iter:
            ner_tags[words[0].word_idx] = f"B-{label}".replace("_", "").upper()
            for w in words[1:]:
                ner_tags[w.word_idx] = f"I-{label}".replace("_", "").upper()

        class_labels.update(ner_tags)
        return ner_tags

    def get_bbox(page, w):
        box = page.get_image_shape(w.box, img_size=(None, MAX_IMAGE_HEIGHT))
        return [box.top.x, box.top.y, box.bot.x, box.bot.y]

    def preprocess_data(examples):
        images = examples["pil_images"]
        words = examples["texts"]
        boxes = examples["bboxes"]
        word_labels = examples["ner_tags"]

        encoded_inputs = processor(
            images,
            words,
            boxes=boxes,
            word_labels=word_labels,
            padding="max_length",
            truncation=True,
            # return_tensors="pt",
            # return_offsets_mapping=True, # TODO, how to add offsets_mapping to the Features
        )

        # close the images as they take a lot of memory
        for img in images:
            img.close()

        return encoded_inputs

    img_size = (None, MAX_IMAGE_HEIGHT)  # All heights have to be fixed
    data_dict = {"id": [], "texts": [], "bboxes": [], "ner_tags": [], "pil_images": []}
    for page in learn_pages:
        data_dict["id"].append(f"{page.doc.pdf_name}-{page.page_idx}")
        data_dict["texts"].append([w.text for w in page.words])
        data_dict["bboxes"].append([get_bbox(page, w) for w in page.words])
        data_dict["ner_tags"].append(get_ner_tags(page))
        data_dict["pil_images"].append(page.page_image.to_pil_image(img_size).convert("RGB"))

        # data_dict["pil_images"].append(get_wand_array(page.page_image))

    check_datset(data_dict)

    ner_tags = data_dict["ner_tags"]

    from datasets import Array2D, Array3D, ClassLabel, Dataset, Features, Sequence, Value
    from transformers import LayoutLMv2Processor

    hf_dataset = Dataset.from_dict(mapping=data_dict)

    sorted_class_labels = sorted(class_labels)
    hf_dataset = hf_dataset.cast_column("ner_tags", Sequence(ClassLabel(names=sorted_class_labels)))

    model_path = model_dir / Path(model_name).name

    if model_path.exists():
        print("MODEL PATH FOUND")
        processor = LayoutLMv2Processor.from_pretrained(
            model_path,
            revision="no_ocr",
            # return_offsets_mapping=True,
        )
    else:
        processor = LayoutLMv2Processor.from_pretrained(
            "microsoft/layoutlmv2-base-uncased",
            revision="no_ocr",
            # return_offsets_mapping=True,
        )

    features = Features(
        {
            "image": Array3D(dtype="int64", shape=(3, 224, 224)),
            "input_ids": Sequence(feature=Value(dtype="int64")),
            "attention_mask": Sequence(Value(dtype="int64")),
            "token_type_ids": Sequence(Value(dtype="int64")),
            "bbox": Array2D(dtype="int64", shape=(512, 4)),
            "labels": Sequence(ClassLabel(names=sorted_class_labels)),
        }
    )
    pt_dataset = hf_dataset.map(
        preprocess_data,
        batched=True,
        remove_columns=hf_dataset.column_names,
        features=features,
    )
    pt_dataset.set_format(type="torch")
    return pt_dataset, sorted_class_labels, ner_tags


@Vision.factory(
    "learn_layoutlmv2",
    requires="labels_dict",
    depends=[
        "transformers[torch]",
        "git+https://github.com/facebookresearch/detectron2.git",
        "seqeval",
        "datasets",
    ],
    default_config={
        "num_folds": 3,
        "max_steps": 100,
        "warmup_ratio": 0.1,
        "publish_name": "",
        "conf_stub": "learn_layout",
        "model_name": "microsoft/layoutlmv2-base-uncased",
    },
)
class LearnLayout:
    def __init__(self, num_folds, max_steps, warmup_ratio, publish_name, conf_stub, model_name):
        self.num_folds = num_folds
        self.max_steps = max_steps
        self.warmup_ratio = warmup_ratio
        self.publish_name = publish_name
        self.conf_stub = conf_stub
        self.model_name = model_name

        self.conf_dir = Path("conf")
        self.model_dir = Path(".model")

        print(f"num_folds: {self.num_folds}")

        self.lgr = logging.getLogger(__name__)
        self.lgr.setLevel(logging.INFO)
        self.lgr.addHandler(logging.StreamHandler())

    def read_word_labels(self, doc):
        def build_region(word_paths):
            words = [doc.get_word(wp) for wp in word_paths]
            assert len(set(w.page_idx for w in words)) == 1
            return Region.build(words, words[0].page_idx)

        doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)
        if not doc_config:
            print(f"NO CONFIG found {self.conf_dir} {doc.pdf_name} {self.conf_stub}")
            return

        doc.add_extra_page_field("word_labels", ("dict_list", "docint.region", "Region"))
        for label, word_paths_lists in doc_config["word_labels"].items():
            wpl = word_paths_lists
            word_paths_list = [wpl] if isinstance(wpl[0], str) else wpl
            label_regions = [build_region(wps) for wps in word_paths_list]

            page = doc[label_regions[0].page_idx]
            if not getattr(page, "word_labels", {}):
                page.word_labels = {}
            page.word_labels[label] = label_regions

        pwl = doc[0].word_labels
        print("---------")
        for label, regions in pwl.items():
            print(f'{label}: {"|".join(r.raw_text() for r in regions)}')
        print("")

    def get_folds(self, num_examples):
        assert (
            num_examples >= self.num_folds and self.num_folds >= 1
        ), f"num_examples: {num_examples} folds: {self.num_folds}"
        assert isinstance(num_examples, int)

        if self.num_folds == 1:
            yield list(range(num_examples)), []
            return

        fold_size = num_examples / self.num_folds
        fold_idxs = [int(i * fold_size) for i in range(self.num_folds)] + [num_examples]

        for (start_idx, end_idx) in pairwise(fold_idxs):
            test_idxs = list(range(start_idx, end_idx))
            train_idxs = list(range(0, start_idx)) + list(range(end_idx, num_examples))
            yield train_idxs, test_idxs

    def print_results(self, test_idxs, actuals, predictions):
        for page_idx, page_actuals, page_predicts in zip(test_idxs, actuals, predictions):
            page_correct = len([(a, t) for (a, t) in zip(page_actuals, page_predicts)])
            print(f"*** {page_idx}: {page_correct} {len(page_actuals)}")

    def run_cross_validation(self, dataset, class_labels, ner_tags):
        import numpy as np
        from datasets import load_metric
        from torch.utils.data import DataLoader
        from transformers import LayoutLMv2ForTokenClassification, Trainer, TrainingArguments

        def compute_metrics(p):
            predictions, labels = p
            predictions = np.argmax(predictions, axis=2)
            # Remove ignored index (special tokens)
            true_predictions = [
                [id2label[p] for (p, l) in zip(prediction, label) if l != -100]  # noqa E741
                for prediction, label in zip(predictions, labels)
            ]
            true_labels = [
                [id2label[l] for (p, l) in zip(prediction, label) if l != -100]  # noqa E741
                for prediction, label in zip(predictions, labels)
            ]
            results = metric.compute(predictions=true_predictions, references=true_labels)
            if return_entity_level_metrics:
                # Unpack nested dictionaries
                final_results = {}
                for key, value in results.items():
                    if isinstance(value, dict):
                        for n, v in value.items():
                            final_results[f"{key}_{n}"] = v
                        else:
                            final_results[key] = value
                return final_results
            else:
                return {
                    "precision": results["overall_precision"],
                    "recall": results["overall_recall"],
                    "f1": results["overall_f1"],
                    "accuracy": results["overall_accuracy"],
                }

        def build_trainer(model, train, test):
            train_loader = DataLoader(train, batch_size=4, shuffle=True)
            test_loader = DataLoader(test, batch_size=2)

            model.config.id2label = id2label
            model.config.label2id = label2id

            class LayoutTrainer(Trainer):
                def get_train_dataloader(self):
                    return train_loader

                def get_test_dataloader(self, test_dataset):
                    return test_loader

            # Initialize our Trainer
            trainer = LayoutTrainer(
                model=model,
                args=args,
                compute_metrics=compute_metrics,
            )
            return trainer

        print(f"Cross Validaton: {self.num_folds}")

        args = TrainingArguments(
            output_dir=self.model_dir / "checkpoints",
            max_steps=self.max_steps,  # we train for a maximum of 1,000 batches #80
            warmup_ratio=self.warmup_ratio,  # we warmup a bit
            fp16=False,  # we use mixed precision (less memory consumption)
            push_to_hub=False,  # after training, we'd like to push our model to the hub
            # push_to_hub_model_id=self.publish_name,
        )

        id2label = {v: k for v, k in enumerate(class_labels)}
        label2id = {k: v for v, k in enumerate(class_labels)}

        for fold_idx, (train_idxs, test_idxs) in enumerate(self.get_folds(len(dataset))):
            print(f"Test[{fold_idx}]: {test_idxs}")
            print(f"Train[{fold_idx}]: {train_idxs}")

            train_dataset = dataset.select(train_idxs)
            test_dataset = dataset.select(test_idxs)

            # Metrics - used in compute_metrics
            metric = load_metric("seqeval")
            return_entity_level_metrics = True

            model_path = self.model_dir / Path(self.model_name).name
            pretrained = LayoutLMv2ForTokenClassification.from_pretrained
            if model_path.exists():
                print("MODEL PATH FOUND")
                model = pretrained(model_path, num_labels=len(class_labels))
            else:
                model = pretrained(
                    "microsoft/layoutlmv2-base-uncased", num_labels=len(class_labels)
                )

            trainer = build_trainer(model, train_dataset, test_dataset)

            trainer.train()
            if self.num_folds > 1:
                predictions, labels, metrics = trainer.predict(test_dataset)
                predictions = np.argmax(predictions, axis=2)
                labeled_predictions = [
                    [id2label[p] for (p, l) in zip(prediction, label) if l != -100]  # noqa E741
                    for prediction, label in zip(predictions, class_labels)
                ]
                doc_labels = [ner_tags[idx] for idx in test_idxs]
                self.print_results(test_idxs, doc_labels, labeled_predictions)
            else:
                predictions, labels, metrics = trainer.predict(train_dataset)
                print(metrics)
                assert not test_idxs
                trainer.save_model(self.model_dir)
            print(f"DONE fold:{fold_idx}")

    def pipe(self, docs, **kwargs):
        self.lgr.info("> infer_layoutlm.pipe")
        print("INSIDE LEARN LAYOUT")
        docs = list(docs)

        for d in docs:
            self.read_word_labels(d)

        learn_pages = [p for d in docs for p in d.pages if hasattr(p, "word_labels")]
        print(f"LEARN PAGES: {len(learn_pages)}")

        hf_dataset, class_labels, ner_tags = generate_dataset(
            learn_pages, self.model_dir, self.model_name
        )

        self.run_cross_validation(hf_dataset, class_labels, ner_tags)
        print(f"Docs: {len(docs)}")
        return docs
