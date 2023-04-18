import json
import logging
import sys
from pathlib import Path

from pydantic.json import pydantic_encoder

from ..shape import Box, Shape
from ..util import get_full_path, get_model_path
from ..vision import Vision


@Vision.factory(
    "table_detector",
    default_config={
        "model_name": "huggingface:TahaDouaji/detr-doc-table-detection",
        "model_dir": "/import/models",
        "output_dir": "output",
    },
)
class TableDetector:
    def __init__(self, model_name, model_dir, output_dir):
        self.model_dir = get_full_path(model_dir)
        self.model_name = model_name
        self.output_dir = Path(output_dir)
        self.conf_stub = "tabledetector"

        from transformers import DetrForObjectDetection, DetrImageProcessor

        table_model_dir = get_model_path(self.model_name, self.model_dir)
        self.processor = DetrImageProcessor.from_pretrained(table_model_dir)
        self.model = DetrForObjectDetection.from_pretrained(table_model_dir)

        self.lgr = logging.getLogger(f"docint.pipeline.{self.conf_stub}")
        self.lgr.setLevel(logging.DEBUG)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        self.lgr.addHandler(stream_handler)

        self.file_handler = None
        self.info_dict = {}

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

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"table_detector: {doc.pdf_name}")
        import torch

        doc.add_extra_page_field("table_boxes", ("list", "docint.shape", "Box"))
        doc.add_extra_page_field("table_boxes_confidence", ("noparse", "", ""))

        json_path = self.output_dir / f"{doc.pdf_name}.{self.conf_stub}.json"
        if json_path.exists():
            json_dict = json.loads(json_path.read_text())
            assert len(doc.pages) == len(json_dict["table_box_infos"])
            for page, table_info in zip(doc.pages, json_dict["table_box_infos"]):
                page.table_boxes = [Box(**d) for d in table_info["table_boxes"]]
                page.table_boxes_confidence = table_info["table_boxes_confidence"]
            self.remove_log_handler(doc)
            return doc

        print(f"Number of pages: {len(doc.pages)}")
        table_infos = []
        for page in doc.pages:
            image = page.page_image.to_pil_image()
            image = image.convert("RGB")

            (width, height) = image.size
            print(f"page_image size: {width}, {height}")

            inputs = self.processor(images=image, return_tensors="pt")
            outputs = self.model(**inputs)

            # convert outputs (bounding boxes and class logits) to COCO API
            # let's only keep detections with score > 0.9
            target_sizes = torch.tensor([image.size[::-1]])
            results = self.processor.post_process_object_detection(
                outputs, target_sizes=target_sizes, threshold=0.9
            )[0]

            page.table_boxes = []
            page.table_boxes_confidence = []
            for score, label, box in zip(results["scores"], results["labels"], results["boxes"]):
                box = [round(i, 2) for i in box.tolist()]
                coord_box = Shape.build_box(
                    [box[0] / width, box[1] / height, box[2] / width, box[3] / height]
                )
                page.table_boxes.append(coord_box)
                page.table_boxes_confidence.append(score.item())

                print(
                    f"Page: [{page.page_idx}] Detected *{self.model.config.id2label[label.item()]}* confidence "
                    f"{round(score.item(), 3)} at location {box}"
                )
            table_infos.append(
                {
                    "table_boxes": page.table_boxes,
                    "table_boxes_confidence": page.table_boxes_confidence,
                }
            )

        json_path.write_text(json.dumps({"table_box_infos": table_infos}, default=pydantic_encoder))

        self.remove_log_handler(doc)
        return doc
