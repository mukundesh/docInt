import html
from pathlib import Path

from more_itertools import flatten

from ..region import Region
from ..shape import Box, Coord, Edge, Poly
from ..table import Table, TableEdges
from ..util import is_writeable_dir
from ..vision import Vision
from ..word import Word

# .officer {
#     fill: blue;
#     fill-opacity: 0.2;
#     stroke: blue;
#     stroke-width: 1;
#     pointer-events: all;

# }

# .post {
#     fill: green;
#     fill-opacity: 0.2;
#     stroke: blue;
#     stroke-width: 1;
#     pointer-events: all;
# }


SVGHeader = """
<svg version="1.1"
    xmlns="http://www.w3.org/2000/svg" width="WIDTH" height="HEIGHT" xmlns:xlink="http://www.w3.org/1999/xlink">

<style type="text/css">

    .item_shape {
        fill: none;
        pointer-events: all;
    }

    .item_shape:hover {
        fill: red;
    }
</style>
<image x="0" y="0" width="WIDTH" height="HEIGHT" xlink:href="IMG_URL"/>
"""

HTMLHeader = """
<!DOCTYPE html PUBLIC"-//W3C//DTD XHTML 1.0 Strict//EN"
        "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
    <meta content="text/html;charset=utf-8" http-equiv="Content-Type"/>
    <meta content="utf-8" http-equiv="encoding"/>
    <title>DOCNAME</title>
</head>
<body>\n"""


@Vision.factory(
    "html_generator",
    default_config={
        "html_root": "output/.html",
        "image_root": "output/.html/.img",
        "svg_stem": "svg",
        "color_dict": {"word": "blue"},
    },
)
class HtmlGenerator:
    def __init__(self, html_root, image_root, svg_stem, color_dict):
        if not is_writeable_dir(html_root):
            raise ValueError(f"Html director {html_root} is not writeable")

        self.html_root = Path(html_root)
        self.image_root = Path(image_root)
        self.svg_stem = svg_stem
        self.color_dict = color_dict

    def get_svg_str(self, object, color, page, path_abbr="", alt_text="", item_name="item_shape"):
        color_str = f'stroke="{color}" fill="{color}" fill-opacity="0.2" stroke-width="1"'
        alt_text = html.escape(alt_text)

        if isinstance(object, Table):
            table = object
            word_strs = []
            for row_idx, col_idx, cell in table.iter_body_cells():
                w_color = color["row2"] if row_idx % 2 == 0 else color["row1"]
                word_strs += [self.get_svg_str(w, w_color, page, item_name=item_name) for w in cell.words]
            return "\n".join(word_strs)
        elif isinstance(object, TableEdges):
            te = object
            r = [
                self.get_svg_str(e, color, page, f"row{i}", f"row{i}", item_name=item_name)
                for i, e in enumerate(te.row_edges)
            ]
            c = [
                self.get_svg_str(e, color, page, f"col{i}", f"col{i}", item_name=item_name)
                for i, e in enumerate(te.col_edges)
            ]
            return "\n".join(r + c)
        elif isinstance(object, Word):
            word = object
            return self.get_svg_str(word.shape, color, page, word.path_abbr, word.text, item_name=item_name)
        elif isinstance(object, Poly) or isinstance(object, Edge):
            coords = object.coords
            path_abbr = path_abbr if path_abbr else object.path_abbr
            img_coords = [page.page_image.get_image_coord(c) for c in coords]
            img_coords_str = " ".join(f"{c.x},{c.y}" for c in img_coords)
            shape_str = f'points="{img_coords_str}"'
            pol_str = f'<polygon class="{item_name}" {shape_str} {color_str}>'
            svg_str = f"{pol_str}<title>{alt_text}</title></polygon>"
            svg_str = f'<a xlink:href="http://{path_abbr}/">{svg_str}</a>'
            return svg_str
        elif isinstance(object, Box):
            box = object
            img_top = page.page_image.get_image_coord(box.top)
            (box_w, box_h) = box.size
            size_coord = Coord(x=box_w, y=box_h)
            img_size_coord = page.page_image.get_image_coord(size_coord)
            img_w, img_h = img_size_coord.x, img_size_coord.y

            shape_str = f'x="{img_top.x}" y="{img_top.y}" width="{img_w}" height="{img_h}"'
            rect_str = f'<rect class="{item_name}" {shape_str} {color_str}>'
            rect_str += f"<title>{alt_text}</title></rect>"
            svg_str = f'<a xlink:href="http://{path_abbr}/">{rect_str}</a>'
            return svg_str
        elif isinstance(object, Region):
            region = object
            return self.get_svg_str(region.shape, color, page, "region", "region", item_name=item_name)
        else:
            raise NotImplementedError(f"not implemented {type(object)}")

    def write_svg(self, page_idx, page, img_url, svg_path):
        def get_items(page, item_name):
            # TODO THIS HAS TO BE JSONPATH
            if item_name == "word":
                return page.words
            elif item_name == "nummarker":
                return page.num_markers
            elif item_name == "table_edges":
                return page.table_edges_list
            elif item_name == "edge":
                return page.edges
            elif item_name == "list_items":
                return page.list_items
            elif item_name == "table":
                return page.tables
            elif item_name == "officer":
                officers = page.doc.order.get_officers(page_idx)
                # return [o for o in officers if len(o.words) > 0 ]
                return flatten(o.words for o in officers if len(o.words) > 0)
            elif item_name == "post":
                posts = page.doc.order.get_posts_page_idx(page_idx)
                # return [p for p in posts if len(p.words) > 0 ]
                return flatten(p.words for p in posts if len(p.words) > 0)
            else:
                raise NotImplementedError(f"not implemented {item_name}")

        # def get_svg(shape, jpath, color, alt_text):
        #     alt_text = html.escape(alt_text)
        #     # color_str = f'stroke="{color}" fill="transparent" stroke-width="1"'
        #     color_str = ""
        #     if shape.is_box():
        #         box = shape
        #         img_top = page.page_image.get_image_coord(box.top)

        #         (box_w, box_h) = box.size
        #         size_coord = Coord(x=box_w, y=box_h)
        #         img_size_coord = page.page_image.get_image_coord(size_coord)
        #         img_w, img_h = img_size_coord.x, img_size_coord.y

        #         shape_str = f'x="{img_top.x}" y="{img_top.y}" width="{img_w}" height="{img_h}"'
        #         svg_str = f'<rect class="item_shape" {shape_str} {color_str}/>'
        #     else:
        #         poly = shape
        #         img_coords = [page.page_image.get_image_coord(c) for c in poly.coords]
        #         img_coords_str = " ".join(f"{c.x},{c.y}" for c in img_coords)
        #         shape_str = f'points="{img_coords_str}"'
        #         pol_str = f'<polygon class="item_shape" {shape_str} {color_str}>'
        #         svg_str = f"{pol_str}<title>{alt_text}</title></polygon>"

        #     svg_item = f'<a xlink:href="http://{jpath}/">{svg_str}</a>'
        #     return svg_item

        with open(svg_path, "w") as svg_file:
            # pw, ph = page.width, page.height
            pw, ph = page.image_size
            svg_file.write(
                SVGHeader.replace(
                    "WIDTH",
                    str(pw),
                )
                .replace("HEIGHT", str(ph))
                .replace("IMG_URL", img_url)
            )
            for (item_name, color) in self.color_dict.items():
                items = get_items(page, item_name)
                svg_strs = [self.get_svg_str(i, color, page, item_name=item_name) for i in items]
                svg_file.write("\t" + "\n\t".join(svg_strs) + "\n")
            svg_file.write("</svg>")

    def check_color(self, color_dict, doc):
        pass

    def __call__(self, doc):
        self.check_color(self.color_dict, doc)
        doc_name = doc.pdf_name

        svgs = []
        for (page_idx, page) in enumerate(doc.pages):
            page_num = page_idx + 1
            angle = getattr(page, "reoriented_angle", 0)
            if angle != 0:
                angle = page.reoriented_angle
                print(f"Page: {page_num} Rotated: {angle}")
                img_path = Path(page.page_image.image_path)
                img_filename = img_path.stem + f"-r{angle}" + img_path.suffix
            else:
                img_filename = Path(page.page_image.image_path).name

            img_url = str(self.image_root / doc.pdf_stem / img_filename)

            svg_filename = Path(f"{self.svg_stem}-{page_num:03}.svg")
            svg_dir_path = self.html_root / doc.pdf_stem
            svg_path = svg_dir_path / svg_filename

            svg_dir_path.mkdir(exist_ok=True, parents=True)
            self.write_svg(page_idx, page, img_url, svg_path)

            html_svg = f'<object data="{doc.pdf_stem}/{svg_path.name}" type="image/svg+xml"></object>'
            svgs.append(html_svg)

        html_path = self.html_root / f"{doc_name}.html"
        print(html_path)
        with open(html_path, "w") as html_file:
            html_header = HTMLHeader.replace("DOCNAME", doc_name)
            html_file.write(html_header)
            pgs = [f"<h1>{doc_name} Page:{idx}</h1>\n\t{svg}" for (idx, svg) in enumerate(svgs)]
            html_file.write("\n".join(pgs))
            html_file.write("\n</html>")
        # end
        return doc
