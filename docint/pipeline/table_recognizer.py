import logging
import sys
from functools import partial, reduce
from itertools import chain
from pathlib import Path

from more_itertools import first, flatten

from ..shape import Coord, Edge
from ..table import TableEdges
from ..util import get_full_path, get_model_path
from ..vision import Vision


@Vision.factory(
    "table_recognizer",
    default_config={
        "model_name": "huggingface:microsoft/table-transformer-structure-recognition",
        "model_dir": "/import/models",
        "merge_threshold_percent": 5,
    },
)
class TableRecognizer:
    def __init__(self, model_name, model_dir, merge_threshold_percent):
        self.model_dir = get_full_path(model_dir)
        self.model_name = model_name
        self.merge_threshold_percent = merge_threshold_percent
        self.conf_stub = "tablerecognizer"

        table_model_dir = get_model_path(self.model_name, self.model_dir)

        from transformers import DetrFeatureExtractor, TableTransformerForObjectDetection

        self.feature_extractor = DetrFeatureExtractor()
        self.model = TableTransformerForObjectDetection.from_pretrained(table_model_dir)

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

    def build_table_edges(self, img, scores, labels, boxes, id2label):
        def merge_coord(coords, coord, cutoff=0.0):
            coord = float(coord)
            if not coords:
                return [coord]

            last_coord = coords[-1]
            if coord - last_coord < cutoff:
                coords[-1] = (last_coord + coord) / 2
            else:
                coords.append(coord)
            return coords

        def build_edge(val, o):
            if o == "h":
                y = val / img.height
                c1, c2 = Coord(x=0.0, y=y), Coord(x=1.0, y=y)
                return Edge(coord1=c1, coord2=c2, orientation="h")
            else:
                x = val / img.width
                c1, c2 = Coord(x=x, y=0.0), Coord(x=x, y=1.0)
                return Edge(coord1=c1, coord2=c2, orientation="v")

        col_code = first([k for (k, v) in id2label.items() if v == "table column"])
        row_code = first([k for (k, v) in id2label.items() if v == "table row"])

        col_boxes = [b for (l, b) in zip(labels, boxes) if l == col_code]  # noqa
        row_boxes = [b for (l, b) in zip(labels, boxes) if l == row_code]  # noqa

        print(f"\tROWS: {len(row_boxes)} COLS: {len(col_boxes)}")

        col_xs = sorted(flatten([b[0], b[2]] for b in col_boxes))
        row_ys = sorted(flatten([b[1], b[3]] for b in row_boxes))

        x_cutoff = (img.width * self.merge_threshold_percent) / 100.0
        y_cutoff = (img.height * self.merge_threshold_percent) / 100.0

        col_merged_xs = reduce(partial(merge_coord, cutoff=x_cutoff), col_xs, [])
        row_merged_ys = reduce(partial(merge_coord, cutoff=y_cutoff), row_ys, [])

        col_edges = [build_edge(x, "v") for x in col_merged_xs]
        row_edges = [build_edge(y, "h") for y in row_merged_ys]

        table_edges = TableEdges(row_edges=row_edges, col_edges=col_edges)
        return table_edges

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"table_recognizer: {doc.pdf_name}")
        import torch

        doc.add_extra_page_field("table_edges_list", ("list", __name__, "TableEdges"))
        doc.add_extra_page_field("edges", ("list", "docint.shape", "Edge"))

        print(f"Number of pages: {len(doc.pages)}")

        for page in doc.pages:
            image = page.page_image.to_pil_image()
            image = image.convert("RGB")

            (width, height) = image.size

            encoding = self.feature_extractor(image, return_tensors="pt")
            with torch.no_grad():
                outputs = self.model(**encoding)

            target_sizes = [image.size[::-1]]
            results = self.feature_extractor.post_process_object_detection(
                outputs, threshold=0.6, target_sizes=target_sizes
            )[0]

            table_edges = self.build_table_edges(
                image,
                results["scores"],
                results["labels"],
                results["boxes"],
                self.model.config.id2label,
            )
            page.table_edges_list = [table_edges]

            page.edges = list(chain(*(t.row_edges for t in page.table_edges_list)))
            page.edges += list(chain(*(t.col_edges for t in page.table_edges_list)))

        self.remove_log_handler(doc)
        return doc


"""
            plot_results(image, results['scores'], results['labels'], results['boxes'])

            def plot_results(pil_img, scores, labels, boxes):
    plt.figure(figsize=(16,10))
    plt.imshow(pil_img)
    ax = plt.gca()
    colors = COLORS * 100
    for score, label, (xmin, ymin, xmax, ymax),c  in zip(scores.tolist(), labels.tolist(), boxes.tolist(), colors):
        ax.add_patch(plt.Rectangle((xmin, ymin), xmax - xmin, ymax - ymin,
                                   fill=False, color=c, linewidth=3))
        text = f'{model.config.id2label[label]}: {score:0.2f}'
        ax.text(xmin, ymin, text, fontsize=15,
                bbox=dict(facecolor='yellow', alpha=0.5))
    plt.axis('off')
    plt.show()

"""
