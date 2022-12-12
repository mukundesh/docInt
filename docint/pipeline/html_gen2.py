import html
from pathlib import Path

from more_itertools import flatten

from ..shape import Coord, Poly
from ..util import is_writeable_dir
from ..vision import Vision

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


SVGHeader = """<svg version="1.1"
    xmlns="http://www.w3.org/2000/svg" viewBox="0 0 WIDTH HEIGHT" xmlns:xlink="http://www.w3.org/1999/xlink">
  <style type="text/css">
.w {
    fill: none;
    stroke: blue;
    stroke-dasharray: 5,5;
    pointer-events: all;
}

.officer {
    fill: blue;
    fill-opacity: 0.2;
    stroke-width: 4;
}

.continues_posts {
    fill: teal;
    fill-opacity: 0.2;
    stroke-width: 4;
    stroke: green;
}

.assumes_posts {
    fill: purple;
    fill-opacity: 0.2;
    stroke-width: 4;
    stroke: green;
}

.relinquishes_posts {
    fill: violet;
    fill-opacity: 0.2;
    stroke-width: 4;
    stroke: green;
}
</style>
<image x="0" y="0" width="WIDTH" height="HEIGHT" xlink:href="IMG_URL"/>
"""


@Vision.factory(
    "html_generator2",
    default_config={
        "svg_root": "output/.html/.img",
        "image_root": "output/.html/.img",
        "css_file": "svg.css",
        "svg_stem": "svg",
    },
)
class HtmlGenerator2:
    def __init__(self, svg_root, image_root, css_file, svg_stem):
        if not is_writeable_dir(svg_root):
            raise ValueError(f"Html director {svg_root} is not writeable")

        self.svg_root = Path(svg_root)
        self.image_root = Path(image_root)
        self.css_file = css_file
        self.svg_stem = svg_stem

    def write_svg(self, page, img_url, svg_path, svg_info):
        def get_poly_str(word, cls_list):
            img_coords = [page.get_image_coord(c) for c in word.coords]
            img_coords_str = " ".join(f"{c.x:.0f},{c.y:.0f}" for c in img_coords)
            shape_str = f'points="{img_coords_str}"'
            pol_str = f'<polygon id="{word.word_idx}" class="{cls_list}" {shape_str}>'
            title_str = html.escape(f"{word.word_idx}-{word.text}")
            svg_str = f"{pol_str}<title>{title_str}</title></polygon>"
            return svg_str

        def get_rect_str(word, cls_list):
            box = word.shape.box
            img_top = page.page_image.get_image_coord(box.top)
            (box_w, box_h) = box.size
            size_coord = Coord(x=box_w, y=box_h)
            img_size_coord = page.page_image.get_image_coord(size_coord)
            img_w, img_h = img_size_coord.x, img_size_coord.y
            shape_str = f'x="{img_top.x}" y="{img_top.y}" width="{img_w}" height="{img_h}"'
            rect_str = f'<rect id="{word.word_idx}" class="{cls_list}" {shape_str}>'
            title_str = html.escape(f"{word.word_idx}-{word.text}")
            rect_str += f"<title>{title_str}</title></rect>"
            return rect_str

        def get_word_str(word, svg_classes):
            cls_list = " ".join(svg_classes)
            if isinstance(word.shape, Poly):
                return get_poly_str(word, cls_list)
            else:
                return get_rect_str(word, cls_list)

        def flatten_list(lst):
            if not lst:
                return []
            elif isinstance(lst[0], list):
                return list(flatten(lst))
            else:
                return lst

        # c_idxs = {}
        # for (c, idx_list) in svg_info.get('idxs', {}).items():
        #     if idx_list and isinstance(idx_list[0], list):
        #         for (pos, idxs) in enumerate(idx_list):
        #             c_idxs[f'{c}{pos}'] = idxs
        #     else:
        #         c_idxs[c] = idx_list

        c_idxs = dict((c, flatten_list(idxs)) for (c, idxs) in svg_info.get("idxs", {}).items())

        with open(svg_path, "w") as svg_file:
            pw, ph = page.image_size
            svg_file.write(
                SVGHeader.replace("WIDTH", f"{pw:.0f}")
                .replace("HEIGHT", f"{ph:.0f}")
                .replace("IMG_URL", img_url)
                .replace("CSSFILE", self.css_file)
            )
            svg_words = []
            for word in page.words:
                svg_classes = [c for (c, idxs) in c_idxs.items() if word.word_idx in idxs]
                svg_classes = ["w"] + svg_classes
                svg_words.append(get_word_str(word, svg_classes))
            svg_file.write("\n".join(svg_words))
            svg_file.write("</svg>")

    def __call__(self, doc):
        first_detail = doc.order.details[0]
        first_svg_info = first_detail.get_svg_info()

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

            if len(str(self.image_root)) > 1:
                img_url = str(self.image_root / doc.pdf_stem / img_filename)
            else:
                img_url = f"p-{page_num:03}.jpg"

            svg_filename = Path(f"{self.svg_stem}-{page_num:03}.svg")
            svg_dir_path = self.svg_root / doc.pdf_stem
            svg_path = svg_dir_path / svg_filename

            svg_dir_path.mkdir(exist_ok=True, parents=True)

            svg_info = first_svg_info if page.page_idx == first_detail.page_idx else {}
            self.write_svg(page, img_url, svg_path, svg_info)
        return doc
