import itertools
import json
import logging
import subprocess
from pathlib import Path

import torch
from datasets import Array2D, Array3D, ClassLabel, Features, Sequence, Value, load_dataset
from PIL import Image, ImageDraw, ImageFont
from torch.utils.data import DataLoader
from tqdm.auto import tqdm
from transformers import LayoutLMv2ForTokenClassification, LayoutLMv2Processor

from ..region import Region
from ..vision import Vision


def drawBoxesAndSave(predictionsList, boxesList, images, imagePaths, imgSaveDir):
    def iob_to_label(label):
        label = label[2:]
        if not label:
            return "other"
        return label

    label2color = {
        "header": "blue",
        "orderdateplace": "green",
        "copystatement": "orange",
        "orderbody": "black",
        "signatoryblock": "red",
        "other": "violet",
    }

    font = ImageFont.load_default()
    imgDirPath = Path(imgSaveDir)

    for predictions, boxes, image, imgPath in zip(predictionsList, boxesList, images, imagePaths):
        draw = ImageDraw.Draw(image)

        for prediction, box in zip(predictions, boxes):
            predicted_label = iob_to_label(prediction).lower()
            draw.rectangle(box, outline=label2color[predicted_label])
            draw.text(
                (box[0] + 10, box[1] - 10),
                text=predicted_label,
                fill=label2color[predicted_label],
                font=font,
            )

        imgPath = Path(imgPath)
        imgSavePath = imgDirPath / (imgPath.stem + ".marked.png")
        image.save(imgSavePath)
    # end for


@Vision.factory(
    "infer_layoutlm",
    default_config={
        "doc_confdir": "conf",
        "page_num": 1,
        "pre_edit": False,
        "post_edit": True,
        "hugging_face_dataset_path": "src/inferDataset.py",
        "layoutlm_dir": "output/layoutlm",
        "model_dir": "input/model",
    },
)
class InferLayoutLM:
    def __init__(
        self,
        doc_confdir,
        page_num,
        pre_edit,
        post_edit,
        hugging_face_dataset_path,
        layoutlm_dir,
        model_dir,
    ):
        self.doc_confdir = doc_confdir
        self.pre_edit = pre_edit
        self.post_edit = post_edit
        self.hugging_face_dataset_path = hugging_face_dataset_path
        self.layoutlm_dir = layoutlm_dir
        self.page_num = 1
        self.model_dir = model_dir

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(logging.StreamHandler())

    def write_layoutlm_json(self, doc, page_idx):
        page = doc[page_idx]
        newWh, newHt = int((page.width * 1000.0) / page.height), 1000

        def flatten_box(box):
            flat_box = [box.top.x, box.top.y, box.bot.x, box.bot.y]
            flat_box = [min(max(v, 0.0), 1.0) for v in flat_box]
            [x0, y0, x1, y1] = flat_box
            flat_box = [
                int(x0 * newWh),
                int(y0 * newHt),
                int(x1 * newWh),
                int(y1 * newHt),
            ]
            [x0, y0, x1, y1] = flat_box
            x0, x1 = x0 if x0 < newWh else newWh - 1, x1 if x1 < newWh else newWh - 1
            y0, y1 = y0 if y0 < newHt else newHt - 1, y1 if y1 < newHt else newHt - 1
            return [x0, y0, x1, y1]

        def build_word(word):
            return {"text": word.text, "box": flatten_box(word.box)}

        print(f"**{doc.pdf_name} {len(doc.pages[0].words)}")

        page_region = Region.build(words=page.words, page_idx=page_idx)
        entity = {
            "id": 0,
            "text": page.text_with_ws,
            "box": flatten_box(page_region.shape),
            "label": "nolabel",
            "linking": [],
            "words": [],
        }
        print("\t** Doing words")

        entity["words"] = [build_word(w) for w in doc.pages[0].words]

        layout_dict = {"form": [entity]}
        json_dir = Path(self.layoutlm_dir) / "annotations"
        json_path = json_dir / Path(doc.pdf_name + ".annot.json")
        json_path.write_text(json.dumps(layout_dict, indent=2))

    def write_layoutlm_image(self, doc, page_idx):
        # page = doc.pages[page_idx]

        input_img_path = doc.get_image_path(page_idx)
        output_img_dir = Path(self.layoutlm_dir) / "images"
        output_img_path = output_img_dir / Path(doc.pdf_name + ".annot.png")
        subprocess.check_call(["convert", "-resize", "x1000", input_img_path, output_img_path])

    def get_pytorch_dataset(self):
        hugging_face_datasets = load_dataset(self.hugging_face_dataset_path)
        selHfDatasets = hugging_face_datasets["validation"]
        # selHfDatasets = hfDatasets['validation'].select(range(11)) #test logic, batch=10

        processor = LayoutLMv2Processor.from_pretrained(
            "microsoft/layoutlmv2-base-uncased",
            revision="no_ocr",
            # return_offsets_mapping=True,
        )

        def preprocess_data(examples):
            images = [Image.open(path).convert("RGB") for path in examples["image_path"]]
            words = examples["words"]
            boxes = examples["bboxes"]
            word_labels = examples["ner_tags"]

            for (path, exWords, exBoxes) in zip(examples["image_path"], words, boxes):
                maxVal = max([max(box) for box in exBoxes])
                if maxVal > 1000:
                    print(f"{path}")
                    for idx, (exWord, exBox) in enumerate(zip(exWords, exBoxes)):
                        if max(exBox) > 1000:
                            print(f"{idx} -> {exWord} {exBox}")
            encoded_inputs = processor(
                images,
                words,
                boxes=boxes,
                word_labels=word_labels,
                padding="max_length",
                truncation=True,
                #            return_offsets_mapping=True, # TODO, how to add offsets_mapping to the Features
            )
            return encoded_inputs

        # Keep imagePaths and docWords as they are lost after encoding
        docWords = [e["words"] for e in selHfDatasets]
        imagePaths = [e["image_path"] for e in selHfDatasets]
        origLabels = selHfDatasets.features["ner_tags"].feature.names

        # we need to define custom features
        features = Features(
            {
                "image": Array3D(dtype="int64", shape=(3, 224, 224)),
                "input_ids": Sequence(feature=Value(dtype="int64")),
                "attention_mask": Sequence(Value(dtype="int64")),
                "token_type_ids": Sequence(Value(dtype="int64")),
                "bbox": Array2D(dtype="int64", shape=(512, 4)),
                "labels": Sequence(ClassLabel(names=origLabels)),
            }
        )
        columnNames = selHfDatasets.column_names
        ptDataset = selHfDatasets.map(
            preprocess_data, batched=True, remove_columns=columnNames, features=features
        )
        ptDataset.set_format(type="torch")
        return ptDataset, docWords, imagePaths

    def eval(self, ptDataset, docWords, imagePaths):
        def grouper(iterable, n, fillvalue=None):
            "Collect data into fixed-length chunks or blocks"
            # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
            args = [iter(iterable)] * n
            return itertools.zip_longest(*args, fillvalue=fillvalue)

        def unnormalize_box(bbox, width, height):
            return [
                width * (float(bbox[0]) / 1000),
                height * (float(bbox[1]) / 1000),
                width * (float(bbox[2]) / 1000),
                height * (float(bbox[3]) / 1000),
            ]

        batchSize = 10
        orderLoader, wordsLoader, imageLoader = (
            DataLoader(ptDataset, batch_size=batchSize),
            grouper(docWords, batchSize),
            grouper(imagePaths, batchSize),
        )

        self.logger.info(f"Evaluating model with batchSize: {batchSize}")

        model = LayoutLMv2ForTokenClassification.from_pretrained(self.model_dir)

        model.eval()
        allDocDicts, allImgPaths = [], []

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        for batch in tqdm(orderLoader, desc="Evaluating"):
            numExamples = len(batch["bbox"])
            wordsBatch = next(wordsLoader)[:numExamples]
            imagePathBatch = next(imageLoader)[:numExamples]
            print("***** New Batch ********")
            print(imagePathBatch)
            with torch.no_grad():
                input_ids = batch["input_ids"].to(device)
                bbox = batch["bbox"].to(device)
                image = batch["image"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                token_type_ids = batch["token_type_ids"].to(device)

                print(f"**** min: {torch.min(bbox)}")
                print(f"**** max: {torch.max(bbox)}")

                # forward pass
                outputs = model(
                    input_ids=input_ids,
                    bbox=bbox,
                    image=image,
                    attention_mask=attention_mask,
                    token_type_ids=token_type_ids,
                )  # no labels

                # offset_mapping = batch["offset_mapping"]
                # is_subword = np.array(offset_mapping.squeeze().tolist())[:, 0] != 0

                # predictions
                labels = batch["labels"].squeeze().tolist()
                labels = [labels] if numExamples == 1 else labels
                predictions = outputs.logits.argmax(dim=2)

                print(f"predictions.shape: {predictions.shape}")
                print(f"len(labels): {len(labels)}")
                print(f"len(labels[0]): {len(labels[0])}")

                # Remove ignored index (special tokens)
                true_predictions = [
                    [
                        model.config.id2label[p.item()]
                        for (lb, p) in zip(label, prediction)
                        if lb != -100
                    ]
                    for label, prediction in zip(labels, predictions)
                ]

                imageBatch = [Image.open(imgPath) for imgPath in imagePathBatch]
                imgSizesBatch = [img.size for img in imageBatch]

                true_boxes = [
                    [
                        unnormalize_box(box, width, height)
                        for (lb, box) in zip(label, boxes)
                        if lb != -100
                    ]
                    for (label, boxes, (width, height)) in zip(labels, batch["bbox"], imgSizesBatch)
                ]

                drawBoxesAndSave(
                    true_predictions,
                    true_boxes,
                    imageBatch,
                    imagePathBatch,
                    "output/images",
                )
                true_words = wordsBatch
                assert len(true_words) == len(true_boxes) == len(true_predictions)

                docDicts = []
                for (doc_preds, doc_words, doc_boxes) in zip(
                    true_predictions, true_words, true_boxes
                ):
                    docDict = {}
                    for (wordIdx, (pred, word, box)) in enumerate(
                        zip(doc_preds, doc_words, doc_boxes)
                    ):
                        wordDict = {"text": word, "box": box, "idx": wordIdx}
                        docDict.setdefault(pred[2:], []).append(wordDict)
                    docDicts.append(docDict)
                allDocDicts.extend(docDicts)
                allImgPaths.extend(imagePathBatch)
        return allDocDicts, allImgPaths

    def pipe(self, docs, **kwargs):
        self.logger.info("Entering infer_layoutlm.pipe")

        docs = list(docs)
        for doc in docs:
            self.write_layoutlm_json(doc, 0)
            self.write_layoutlm_image(doc, 0)

        doc_dict = dict([(doc.pdf_name, doc) for doc in docs])
        self.logger.info("Done saving layoutlm files")

        ptDataset, docWords, imagePaths = self.get_pytorch_dataset()

        self.logger.info("Generated pytorch dataset")

        allDocDicts, allImgPaths = self.eval(ptDataset, docWords, imagePaths)

        for imgPath, docDict in zip(allImgPaths, allDocDicts):
            pdf_name = Path(imgPath).name.replace(".annot.png", "")
            doc = doc_dict[pdf_name]

            doc.add_extra_page_field("layoutlm", ("dict", "docint.region", "Region"))
            page = doc[self.page_num - 1]
            page.layoutlm = {}

            page = doc[0]
            print(f"{pdf_name} ****************")
            for label, wordDicts in docDict.items():
                words = [
                    page[w["idx"]]
                    for w in wordDicts
                    if w["idx"] < len(page.words) and w["idx"] >= 0
                ]

                wrong_idxs = [
                    w["idx"] for w in wordDicts if (w["idx"] >= len(page.words)) or (w["idx"] < 0)
                ]
                if wrong_idxs:
                    print(f'WRONG IDXS: {" ".join(str(idx) for idx in wrong_idxs)}')

                page.layoutlm[label] = Region.build(words=words, page_idx=0)
                print(f"{label}")
                print(f"{page.layoutlm[label].raw_text()}")
                print("")
        # end for
        return docs
