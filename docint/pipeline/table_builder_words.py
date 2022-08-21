import logging
import sys
from itertools import chain, groupby
from operator import attrgetter, itemgetter
from pathlib import Path

from ..region import Region

# from ..table import Table, Row, Cell
from ..shape import Edge
from ..vision import Vision


@Vision.factory(
    "table_builder_on_words",
    default_config={
        "doc_confdir": "conf",
        "conf_stub": "table",
        "pdfplumber_config": {"strategy": "text"},
    },
)
class TableBuilderOnWords:
    def __init__(
        self,
        doc_confdir,
        conf_stub,
        pdfplumber_config,
    ):
        self.doc_confdir = doc_confdir
        self.conf_stub = conf_stub
        self.pdfplumber_config = pdfplumber_config

        self.tolerance = 0.02
        self.edge_min_length = 0.2
        self.word_threshold = 3

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

    def cluster_words(self, words, attr, tolerance):
        cluster_attr = attrgetter(attr)
        sorted_words = sorted(words, key=cluster_attr)

        if len(words) == 0:
            return []

        firstWord = sorted_words[0]
        if len(words) == 1:
            return [firstWord]

        clusters, current_cluster = [], [firstWord]
        last_val = cluster_attr(firstWord)

        for w in sorted_words[1:]:
            w_val = cluster_attr(w)

            if w_val <= last_val + tolerance:
                current_cluster.append(w)
            else:
                clusters.append(current_cluster)
                current_cluster = [w]
                last_val = w_val
        # end
        clusters.append(current_cluster)
        return clusters

    def merge_edges(self, edges, snap_tolerance, join_tolerance):
        def snap(edges, attr, tolerance):
            pass

        def join_edge_group(edges, orientation, tolerance):
            if orientation == "h":
                min_prop, max_prop = "xmin", "xmax"
            else:
                min_prop, max_prop = "ymin", "ymax"

            sorted_edges = sorted(edges, key=itemgetter(min_prop))
            joined = sorted_edges[0]
            for e in sorted_edges[1:]:
                last = joined[-1]
                if e[min_prop] <= (last[max_prop] + tolerance):
                    if e[max_prop] > last[max_prop]:
                        # Extend current edge to new extremity
                        pass
                        # joined[-1] = utils.resize_object(last, max_prop, e[max_prop])
                else:
                    # Edge is separate from previous edges
                    joined.append(e)
            return joined

        def get_group(edge):
            return ("h", edge.ymin) if edge.orientation == "h" else ("v", edge.xmin)

        def snap_edges(edges, tolerance=self.snap_tolerance):
            v, h = [[e for e in edges if e.orientation == o] for o in ("h", "v")]

            snapped = snap(v, "xmin", tolerance) + snap(h, "ymin", tolerance)
            return snapped

        if snap_tolerance > 0:
            edges = snap_edges(edges, snap_tolerance)

        if join_tolerance > 0:
            sorted_edges = sorted(edges, key=get_group)
            edge_groups = groupby(sorted_edges, key=get_group)
            edge_gen = (join_edge_group(items, k[0], join_tolerance) for k, items in edge_groups)
            edges = list(chain(*edge_gen))
        return edges

    def build_v_edges(self, table_words):
        cluster_lt = self.cluster_words(table_words, "xmin", self.tolerance)
        cluster_rt = self.cluster_words(table_words, "xmax", self.tolerance)
        cluster_md = self.cluster_words(table_words, "xmid", self.tolerance)

        clusters = cluster_lt + cluster_rt + cluster_md

        sorted_clusters = sorted(clusters, key=lambda c: -len(c))
        large_clusters = [c for c in sorted_clusters if len(c) > self.word_threshold]

        regions = [Region(words=c) for c in large_clusters]
        non_overlapping_regions = []
        for region in regions:
            overlaps = False
            for r in non_overlapping_regions:
                if region.shape.overlaps(r.shape):
                    overlaps = True
                    break
            if not overlaps:
                non_overlapping_regions.append(region)

        if len(non_overlapping_regions) == 0:
            return []

        print(len(non_overlapping_regions))

        sorted_regions = list(sorted(non_overlapping_regions, key=attrgetter("xmin")))
        max_xmax = max(r.xmax for r in sorted_regions)
        min_ymin = min(r.ymin for r in sorted_regions)
        max_ymax = min(r.ymax for r in sorted_regions)

        edges = [Edge.build_v(r.xmin, min_ymin, r.xmax, max_ymax) for r in sorted_regions]

        edges += [Edge.build_v(max_xmax, min_ymin, max_xmax, max_ymax)]
        return edges

    def build_h_edges(self, table_words):
        cluster_top = self.cluster_words(table_words, "ymin", self.tolerance)
        large_clusters = [c for c in cluster_top if len(c) > self.word_threshold]

        regions = [Region(words=c) for c in large_clusters]
        if len(regions) == 0:
            return []

        min_xmin = min(r.xmin for r in regions)
        max_xmax = max(r.xmax for r in regions)
        max_ymax = max(r.ymax for r in regions)

        edges = [Edge.build_h(min_xmin, r.ymin, max_xmax, r.ymax) for r in regions]
        edges += [Edge.build_h(min_xmin, max_ymax, max_xmax, max_ymax)]
        return edges

    def build_edges(self, table_words):
        edges = self.build_v_edges(table_words)  # + self.build_h_edges(table_words)
        self.lgr.info(f"Total Edges: {len(edges)}")
        # edges = self.merge_edges(edges)
        edges = [e for e in edges if e.length > self.edge_min_length]
        return edges

    def __call__(self, doc):
        self.add_log_handler(doc)
        self.lgr.info(f"table_finder: {doc.pdf_name}")

        doc.add_extra_page_field("edges", ("list", "docint.shape", "Edge"))

        for page in doc.pages:
            ymin, ymax = page.num_markers[0].ymin, page.num_markers[-1].ymax
            table_words = page.words_in_yrange((ymin, ymax), partial=True)
            page.edges = self.build_edges(table_words)
        self.remove_log_handler(doc)
        return doc


"""

    def build_tables(table_words):
        edges = self.build_edges(table_words)

        intersections = edges_to_intersections(edges)
        cells = interesections_to_cells(intersections)
        tables = cells_to_tables(cells)

    def edges_to_intersections(edges, x_tolerance, y_tolerance):
        v_edges, h_edges = [ [e for e in edges if e.orientation == o] for o in ('h', 'v')]

        intersections = {}
        for v in sorted(v_edges, key=itemgetter('xmin', 'ymin')):
            for h in sorted(h_edges, key=itemgetter('ymin', 'xmin')):
                if ((v.ymin <= h.ymin + y_tolerance) and
                (v.ymax >= h.ymin - y_tolerance) and
                (v.xmin >= hxmin - x_tolerance) and
                (v.xmin <= h.xmax + x_tolerance):
                ):
                    vertex = Coord(x=v.xmin, y=h.ymin)
                    if vertex not in intersections:
                        intersections[vertex] = {'v': [], 'h':[]}
                    intersections[vertex]['v'].append(v)
                    intersections[vertex]['h'].append(h)
        #end for
        return intersections

    def intersections_to_cells(intersections):
        def edges_to_set(edges):
            return set(e for e in edges)


        def edge_connects(c1, c2):
            if c1.x == c2.x:
                common = edges_to_set(intersections[c1]['v']).interesection(edges_to_set(interesection[c2]['v']))
                if len(common):
                    return True

            if c1.y == c2.y:
                common = edges_to_set(intersections[c1]['h']).interesection(edges_to_set(interesection[c2]['h']))
                if len(common):
                    return True
            return False

        def find_smallest_cell(coords, idx):
            if idx == len(points) -1:
                return None

            c = coords[idx]
            rest = coords[idx+1:]

            below = [r for r in rest if r.x == c.x]
            right = [r for r in rest if r.y == c.y]

            for below_c in below:
                if not edge_connects(c, below_c):
                    continue

                for right_c in right:
                    if not edge_connects(c, right_c):
                        continue
                    bottom_right = Coord(x=right_c.x, y=below_c.y)
                    if (bottom_right in intersections and
                        edge_connects(bottom_right, right_c) and
                        edge_connects(bottom_right, below_c)):

                        return (c.x, c.y, bottom_right.x, bottom_right.y)

        coords = sorted(intersections.keys())
        cell_gen = (find_smallest_cell(coords, idx) for idx in range(len(coords)))
        return list(filter(None, cell_gen))

    def cells_to_tables(cells):
        pass

"""
