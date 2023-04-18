import logging
from pathlib import Path

from more_itertools import pairwise

from docint.span import Span

# from more_itertools import pairwise
from docint.util import get_full_path, get_model_path, load_config
from docint.vision import Vision

# TODO: 1. Model save options locally, huggingface cloud
# TODO: 2 Save the results and verify the model is correct


def get_text_paras(docs):
    for page in [p for d in docs for p in d.pages]:
        text_paras = getattr(page, "text_paras", [])
        for idx, para in enumerate(text_paras):
            yield f"{page.doc.pdf_name}-{page.page_idx}-{idx}", para


def get_ner_tags(labels):
    ner_tags = []
    for (idx, label) in enumerate(labels):
        if label is None:
            ner_tags.append("O")
            continue

        stub = "OFF" if label == "officer" else "DEP"
        if idx == 0 or label != labels[idx - 1]:
            ner_tags.append(f"B-{stub}")
        else:
            ner_tags.append(f"I-{stub}")
    return ner_tags


##def check_datset(data_dict):
# num_examples = len(data_dict["id"])
# assert all(len(v) == num_examples for v in data_dict.values())

# zip_iter = zip(data_dict["texts"], data_dict["bboxes"], data_dict["ner_tags"])
# assert all(len(t) == len(b) == len(n) for (t, b, n) in zip_iter)

# max_val = MAX_IMAGE_HEIGHT
# for page_id, example in zip(data_dict["id"], data_dict["bboxes"]):
#     for idx, box in enumerate(example):
#         for coord_val in box:
#             assert (
#                 0 <= coord_val <= max_val
#             ), f"incorrect coord_val: {coord_val} {page_id} word: {idx}"

# assert all(0 <= c <= max_val for e in data_dict["bboxes"] for b in e for c in b)
# assert all(len(b) == 4 for e in data_dict["bboxes"] for b in e)
# assert all(i.size[0] <= i.size[1] == max_val for i in data_dict["pil_images"])


@Vision.factory(
    "learn_ner",
    requires="labels_dict",
    depends=[
        "transformers[torch]",
        "seqeval",
        "datasets",
    ],
    default_config={
        "num_folds": 3,
        "max_steps": 100,
        "warmup_ratio": 0.1,
        "publish_name": "",
        "conf_stub": "ner",
        "model_dir": ".model",
        "orig_model_name": "huggingface:distilbert-base-uncased",
        "save_model_name": "orgpedia:orgpedia-foundation/rajpol-dept-ner",
    },
)
class LearnNER:
    def __init__(
        self,
        num_folds,
        max_steps,
        warmup_ratio,
        publish_name,
        conf_stub,
        model_dir,
        orig_model_name,
        save_model_name,
    ):
        self.num_folds = num_folds
        self.max_steps = max_steps
        self.warmup_ratio = warmup_ratio
        self.publish_name = publish_name
        self.conf_stub = conf_stub
        self.ner_model_name = orig_model_name
        self.save_model_name = save_model_name

        self.conf_dir = Path("conf")
        self.model_dir = get_full_path(model_dir)

        from transformers import AutoTokenizer

        self.ner_model_dir = get_model_path(self.ner_model_name, self.model_dir)

        self.tokenizer = AutoTokenizer.from_pretrained(self.ner_model_dir)

        self.save_model_dir = get_model_path(self.save_model_name, self.model_dir)

        print(f"num_folds: {self.num_folds}")

        self.lgr = logging.getLogger(__name__)
        self.lgr.setLevel(logging.INFO)
        self.lgr.addHandler(logging.StreamHandler())

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

    def add_para_spans(self, doc):
        doc_config = load_config(self.conf_dir, doc.pdf_name, self.conf_stub)

        for para_config in doc_config["page_configs"]:  # please correct t his
            if "ignore" in para_config:
                continue

            para = doc[para_config["page_idx"]].text_paras[para_config["para_idx"]]
            para.clear_labels()

            for (label, spans) in para_config.items():
                if label == "para_idx" or label == "page_idx":
                    continue

                if not spans or not spans[0]:
                    continue

                for (start, end) in spans:
                    span = Span(start=start, end=end)
                    para.add_label(span, label)
                    print(f"Adding {label}: {span}")

    # https://github.com/huggingface/notebooks/blob/main/examples/token_classification.ipynb
    def tokenize_and_align_labels(self, examples):
        tokenized_inputs = self.tokenizer(
            examples["tokens"], truncation=True, is_split_into_words=True
        )
        label_all_tokens = True
        labels = []
        for i, label in enumerate(examples["ner_tags"]):
            word_ids = tokenized_inputs.word_ids(batch_index=i)
            previous_word_idx = None
            label_ids = []
            for word_idx in word_ids:
                # Special tokens have a word id that is None.
                # We set the label to -100 so they are automatically
                # ignored in the loss function.
                if word_idx is None:
                    label_ids.append(-100)
                    # We set the label for the first token of each word.
                elif word_idx != previous_word_idx:
                    label_ids.append(label[word_idx])
                    # For the other tokens in a word, we set the label to
                    # either the current label or -100, depending on
                    # the label_all_tokens flag.
                else:
                    label_ids.append(label[word_idx] if label_all_tokens else -100)
                previous_word_idx = word_idx

            labels.append(label_ids)

        tokenized_inputs["labels"] = labels
        return tokenized_inputs

    def generate_dataset(self, docs):
        data_dict = {"id": [], "tokens": [], "ner_tags": []}
        class_labels = set()

        for (para_id, para) in get_text_paras(docs):
            data_dict["id"].append(para_id)

            tokens, labels = para.get_texts_labels(para)
            print(tokens)
            print(labels)

            data_dict["tokens"].append(tokens)

            ner_tags = get_ner_tags(labels)
            data_dict["ner_tags"].append(ner_tags)
            class_labels.update(ner_tags)

            assert len(data_dict["tokens"][-1]) == len(data_dict["ner_tags"][-1])

        sorted_class_labels = sorted(class_labels)  # + ["B-LOC", "I-LOC", "B-MISC", "I-MISC"]
        class_labels = sorted_class_labels

        from datasets import ClassLabel, Dataset, Features, Sequence, Value

        features = Features(
            {
                "id": Value("string"),
                "tokens": Sequence(Value("string")),
                "ner_tags": Sequence(ClassLabel(names=class_labels)),
            }
        )

        # dataset = Dataset.from_dict(mapping=data_dict, features)
        dataset = Dataset.from_dict(data_dict, features)

        print(sorted_class_labels)
        # dataset = dataset.cast_column("ner_tags", Sequence(ClassLabel(names=sorted_class_labels)))

        print("DATASET GENERATED")

        tokenized_dataset = dataset.map(self.tokenize_and_align_labels, batched=True)

        return tokenized_dataset, sorted_class_labels

    def run_cross_validation(self, dataset, class_labels):
        def compute_metrics(p):
            predictions, labels = p
            predictions = np.argmax(predictions, axis=2)

            # Remove ignored index (special tokens)
            true_predictions = [
                [class_labels[p] for (p, l) in zip(prediction, label) if l != -100]  # noqa
                for prediction, label in zip(predictions, labels)
            ]
            true_labels = [
                [class_labels[l] for (p, l) in zip(prediction, label) if l != -100]  # noqa
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

        import numpy as np
        import seqeval  # noqa
        from datasets import load_metric
        from transformers import (
            AutoModelForTokenClassification,
            DataCollatorForTokenClassification,
            Trainer,
            TrainingArguments,
        )

        model = AutoModelForTokenClassification.from_pretrained(
            self.ner_model_dir, num_labels=len(class_labels)
        )

        batch_size = 8

        id2label = {v: k for v, k in enumerate(class_labels)}
        label2id = {k: v for v, k in enumerate(class_labels)}
        return_entity_level_metrics = True  # CHANGE THIS

        args = TrainingArguments(
            self.save_model_name,
            evaluation_strategy="steps",
            learning_rate=2e-5,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            num_train_epochs=5,  # change this
            logging_steps=10,  # change this from 1000
            report_to="wandb",
            weight_decay=0.01,
            push_to_hub=False,
        )

        data_collator = DataCollatorForTokenClassification(self.tokenizer)
        for fold_idx, (train_idxs, test_idxs) in enumerate(self.get_folds(len(dataset))):
            print(f"Test[{fold_idx}]: {test_idxs}")
            print(f"Train[{fold_idx}]: {train_idxs}")

            train_dataset = dataset.select(train_idxs)
            test_dataset = dataset.select(test_idxs)

            metric = load_metric("seqeval")

            model.config.id2label = id2label
            model.config.label2id = label2id

            trainer = Trainer(
                model,
                args,
                train_dataset=train_dataset,
                eval_dataset=test_dataset,
                data_collator=data_collator,
                tokenizer=self.tokenizer,
                compute_metrics=compute_metrics,
            )
            trainer.train()
            predictions, labels, metrics = trainer.predict(test_dataset)
            if self.num_folds > 1:
                predictions, labels, metrics = trainer.predict(test_dataset)
                predictions = np.argmax(predictions, axis=2)
                labeled_predictions = [  # noqa
                    [id2label[p] for (p, l) in zip(prediction, label) if l != -100]  # noqa E741
                    for prediction, label in zip(predictions, class_labels)
                ]
                # doc_labels = [class_labels[idx] for idx in test_idxs]
                # self.print_results(test_idxs, doc_labels, labeled_predictions)
            else:
                predictions, labels, metrics = trainer.predict(train_dataset)
                print(metrics)
                assert not test_idxs
                trainer.save_model(self.save_model_dir)
            print(f"DONE fold:{fold_idx}")

    def pipe(self, docs, **kwargs):
        self.lgr.info("> infer_layoutlm.pipe")
        print("INSIDE LEARN LAYOUT")
        docs = list(docs)

        for doc in docs:
            self.add_para_spans(doc)

        dataset, class_labels = self.generate_dataset(docs)  # noqa

        self.run_cross_validation(dataset, class_labels)

        return docs


"""
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


"""


"""
from transformers import AutoTokenizer, DataCollatorForTokenClassification, AutoModelForTokenClassification, TrainingArguments, Trainer
tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
data_collator = DataCollatorForTokenClassification(tokenizer=tokenizer)
model = AutoModelForTokenClassification.from_pretrained("distilbert-base-uncased", num_labels=len(dm.unique_entities), id2label=dm.id2label, label2id=dm.label2id)
"""
