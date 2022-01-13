import pathlib

from ..vision import Vision
from ..util import is_writeable_dir

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
        "color_dict": {"word": "blue"},
    },
)
class HtmlGenerator:
    def __init__(self, html_root, image_root, color_dict):
        if not is_writeable_dir(html_root):
            raise ValueError(f"Html director {html_root} is not writeable")

        self.html_root = pathlib.Path(html_root)
        self.color_dict = color_dict
        self.image_root = pathlib.Path(image_root)

    def write_svg(self, page_idx, page, img_url, svg_path):
        def get_items(page, item_name):
            ## TODO THIS HAS TO BE JSONPATH
            if item_name == "word":
                return page.words
            elif item_name == "nummarker":
                return page.num_markers
            else:
                raise NotImplementedError(f'not implemented {item_name}')

        def get_svg(shape, jpath, color):
            color_str = f'stroke="{color}" fill="transparent" stroke-width="1"'
            if shape.is_box():
                box = shape
                top = box.top_inpage(page.size)
                (sw, sh) = box.size_inpage(page.size)
                shape_str = f'x="{top.x}" y="{top.y}" width="{sw}" height="{sw}"'
                svg_str = f'<rect class="item_shape" {shape_str} {color_str}/>'
            else:
                poly = shape
                shape_str = f'points="{poly.get_coords_inpage(page.size)}"'
                svg_str = f'<polygon class="item_shape" {shape_str} {color_str}/>'
            svg_item = f'<a xlink:href="http://{jpath}/">{svg_str}</a>'
            return svg_item

        with open(svg_path, 'w') as svg_file:
            pw, ph = page.width, page.height
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
                svg_strs = [get_svg(i.shape, i.path_abbr, color) for i in items]
                svg_file.write("\t" + "\n\t".join(svg_strs))
            svg_file.write("</svg>")

    def check_color(self, color_dict, doc):
        pass

    def __call__(self, doc):
        self.check_color(self.color_dict, doc)
        doc_name = doc.pdf_name

        svgs = []
        for (page_idx, page) in enumerate(doc.pages):
            page_num, doc_stub = page_idx + 1, doc_name[:-4]
            img_filename = pathlib.Path(f"orig-{page_num:03d}-000.png")
            img_url = str(self.image_root / doc_stub / img_filename)
            
            svg_filename = pathlib.Path(f"svg-{page_num:03}.svg")
            svg_path = self.html_root / doc_stub / svg_filename
            
            self.write_svg(page_idx, page, img_url, svg_path)

            html_svg = f'<object data="{doc_stub}/{svg_path.name}" type="image/svg+xml"></object>'
            svgs.append(html_svg)

        html_path = self.html_root / f"{doc_name}.html"
        with open(html_path, 'w') as html_file:
            html_header = HTMLHeader.replace("DOCNAME", doc_name)
            html_file.write(html_header)
            pgs = [f"<h1>{doc_name} Page:{idx}</h1>\n\t{svg}" for (idx, svg) in enumerate(svgs)]
            html_file.write("\n".join(pgs))
            html_file.write("\n</html>")
        # end
        return doc
