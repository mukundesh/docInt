import pathlib
import json
from dataclasses import dataclass

import pdfplumber
import pdf2image
import pydantic

from .shape import Shape, Box, Coord

# A container for tracking the document from a pdf/image to extracted information.


@dataclass
class PageImage:
    image_width: float
    image_height: float
    image_path: str
    image_box: Box
    image_type: str

@dataclass
class PageInfo:
    width: float
    height: float
    num_images: int


class Doc:
    image_dirs_path = ".img"

    def __init__(self, pdffile_path, user_data=None):
        self.pdffile_path = pathlib.Path(pdffile_path)
        self.user_data = {} if user_data is None else user_data
        self.pages = []        
        self.page_infos = []
        self.page_images = []

    def __getitem__(self, idx):
        if isinstance(idx, slice) or isinstance(idx, int):
            return self.pages[idx]
        else:
            raise TypeError("Unknown type {type(idx)} this method can handle")

    def to_dict(self):
        pass


    @property
    def num_pages(self):
        return len(self.page_images)

    @property
    def pdf_path(self):
        return self.pdffile_path

    @property
    def pdf_stem(self):
        return self.pdffile_path.stem

    @property
    def pdf_name(self):
        return self.pdffile_path.name

    @property
    def has_images(self):
        return sum([i.num_images for i in self.page_infos]) > 0

    # move this to document factory
    @classmethod
    def build_doc(cls, pdf_path, image_dirs_path=None):
        def rasterize_page(pdf_path, image_dir_path, page_idx):
            page_num = page_idx + 1
            output_filename = f"orig-{page_num:03d}-000"

            images = pdf2image.convert_from_path(
                pdf_path=pdf_path,
                output_folder=image_dir_path,
                dpi=300,
                first_page=page_num,
                last_page=page_num,
                fmt="png",
                single_file=True,
                output_file=output_filename,
                # paths_only=True,
            )
            # assert len(images) == 1 TODO  NEED TO PUT THIS IN TRY BLOCK
            (width, height) = images[0].size
            return f"{output_filename}.png", width, height

        pdf_path = pathlib.Path(pdf_path)
        image_dir_name = pdf_path.name.lower()[:-4]

        image_dirs_path = (
            cls.image_dirs_path if not image_dirs_path else image_dirs_path
        )
        image_dirs_path = pathlib.Path(image_dirs_path)
        image_dir_path = image_dirs_path / image_dir_name

        doc = Doc(pdf_path)
        pdf_info_path = image_dir_path / (doc.pdf_name + ".pdfinfo.json")

        if image_dir_path.exists() and pdf_info_path.exists():
            pdf_info = json.loads(pdf_info_path.read_text())
            doc.page_infos = [PageInfo(**p) for p in pdf_info["page_infos"]]
            doc.page_images = [PageImage(**i) for i in pdf_info["page_images"]]
            return doc

        image_dir_path.mkdir(exist_ok=True, parents=True)
        pdf = pdfplumber.open(pdf_path)
        for (page_idx, page) in enumerate(pdf.pages):
            doc.page_infos.append(PageInfo(page.width, page.height, len(page.images)))

            # TODO: check the size of page image and extract only if it is big
            if len(page.images) == 1:
                img = page.images[0]
                width, height = tuple(map(int, img["srcsize"]))
                coords = [ Coord(img['x0'], img['y0']), Coord(img['x1'], img['y1']) ]
                image_box = coords 
                image_path = cls._extract_image(pdf_path, image_dir_path, page_idx)
                image_type = "original"
            else:
                image_path, width, height = rasterize_page(
                    pdf_path, image_dir_path, page_idx
                )
                [x0, y0, x1, y1] = page.bbox
                coords = [ Coord(x0, y0), Coord(x1, y1)]
                image_box = coords 
                image_type = "raster"
            page_image = PageImage(width, height, image_path, image_box, image_type)
            doc.page_images.append(page_image)
        # end
        pdf_info = {"page_infos": doc.page_infos, "page_images": doc.page_images}
        pdf_info_path.write_text(json.dumps(pdf_info, default=pydantic.json.pydantic_encoder))
        return doc

    def to_json(self):
        return 'JSON HAHAHAH '

    def edit(self, edits):
        pass

    @property
    def doc(self):
        return self

