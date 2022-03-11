from dataclasses import dataclass
from importlib import import_module
import subprocess
from typing import List, Tuple, Dict

from pydantic import BaseModel, Field, parse_obj_as

from pathlib import Path
import json
import shlex

import pdfplumber
import pdf2image
import pydantic
import msgpack

from .shape import Shape, Box, Coord
from .page import Page
from .region import Region


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


class Doc(BaseModel):
    pdffile_path: Path
    pages: List[Page] = [] #field(default_factory=list)
    page_infos: List[PageInfo] = [] #field(default_factory=list)
    page_images: List[PageImage] = [] #field(default_factory=list)
    extra_fields: Dict[str, Tuple] = {}
    extra_page_fields: Dict[str, Tuple] = {}

    class Config:
        extra = 'allow'
    

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

    def get_image_path(self, page_idx):
        page_num = page_idx + 1
        image_dir = root_dir / self.pdf_stem
        angle = getattr(self.pages[page_idx], 'reoriented_angle', 0)
        if angle != 0:
            return  image_dir / f"orig-{page_num:03d}-000-r{angle}.png"
        else:
            return  image_dir / f"orig-{page_num:03d}-000.png"

    # move this to document factory
    @classmethod
    def build_doc(cls, pdf_path, image_dirs_path):
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

        def extract_image(pdf_path, image_dir_path, page_idx):
            pdf_path = str(pdf_path)
            image_root = f"{str(image_dir_path)}/orig"
            page_num = page_idx + 1
            output_path = f"orig-{page_num:03d}-000.png"
            subprocess.check_call(
                ["pdfimages", "-f", str(page_num), "-l", str(page_num), "-p", "-png", pdf_path, image_root]
            )
            return output_path
        

        pdf_path = Path(pdf_path)
        image_dir_name = pdf_path.name[:-4]

        image_dirs_path = (
            cls.image_dirs_path if not image_dirs_path else image_dirs_path
        )
        image_dirs_path = Path(image_dirs_path)
        image_dir_path = image_dirs_path / image_dir_name

        doc = Doc(pdffile_path=pdf_path)
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

            # TODO: check the shape of page image and extract only if it covers full page
            if len(page.images) == 1:
                img = page.images[0]
                width, height = tuple(map(int, img["srcsize"]))
                top, bot = Coord(x=img["x0"], y=img["y0"]), Coord(x=img["x1"], y=img["y1"])
                image_box = Box(top=top, bot=bot)
                image_path = extract_image(pdf_path, image_dir_path, page_idx)
                image_type = "original"
            else:
                image_path, width, height = rasterize_page(
                    pdf_path, image_dir_path, page_idx
                )
                [x0, y0, x1, y1] = page.bbox
                top, bot = Coord(x=x0, y=y0), Coord(x=x1, y=y1)
                image_box = Box(top=top, bot=bot)
                image_type = "raster"
            page_image = PageImage(width, height, image_path, image_box, image_type)
            doc.page_images.append(page_image)
        # end
        pdf_info = {"page_infos": doc.page_infos, "page_images": doc.page_images}
        pdf_info_path.write_text(
            json.dumps(pdf_info, default=pydantic.json.pydantic_encoder, indent=2)
        )
        return doc

    def to_json(self):
        return self.json(models_as_dict=False, indent=2)

    def to_msgpack(self):
        import msgpack
        return msgpack.packb(json.loads(self.to_json()))

    def to_disk(self, disk_file):
        disk_file = Path(disk_file)
        if disk_file.suffix.lower() in ('.json', '.jsn'):
            disk_file.write_text(self.to_json())
        else:
            disk_file.write_bytes(self.to_msgpack())

    def add_extra_page_field(self, field_name, field_tuple):
        self.extra_page_fields[field_name] = field_tuple

    def add_extra_field(self, field_name, field_tuple):
        self.extra_fields[field_name] = field_tuple
    

    @classmethod
    def from_disk(cls, json_file):
        def get_extra_fields(obj):
            all_fields = set(obj.dict().keys())
            def_fields = set(obj.__fields__.keys())
            return all_fields.difference(def_fields)

        def update_links(doc, regions):
            if regions and not isinstance(regions[0], Region):
                return 

            inner_regions = [ ir for r in regions for ir in r.get_regions() ]
            for region in inner_regions:
                region.words = [doc[w.page_idx][w.word_idx] for w in region.words]
                if region.word_lines:
                    region.word_lines = [[doc[w.page_idx][w.word_idx] for w in wl] for wl in region.word_lines]

        json_file = Path(json_file)
        if json_file.suffix.lower() in ('.json', '.jsn'):
            doc_dict = json.loads(json_file.read_text())
        else:
            doc_dict = msgpack.unpackb(json_file.read_bytes())
        new_doc = Doc(**doc_dict)

        # link doc to page and words
        for page in new_doc.pages:
            page.doc = new_doc
            for word in page.words:
                word.doc = new_doc

        # link word to word_lines to actual words
        for page in new_doc.pages:
            for extra_field, field_tuple in new_doc.extra_page_fields.items():
                extra_attr_dict = getattr(page, extra_field, None)
                if not extra_attr_dict:
                    continue
                (extra_type, module_name, class_name) = field_tuple
                if extra_type == 'obj':
                    cls = getattr(import_module(module_name), class_name)                
                    extra_attr_obj = parse_obj_as(cls, extra_attr_dict)
                    update_links(new_doc, [extra_attr_obj])
                elif extra_type == 'list':
                    cls = getattr(import_module(module_name), class_name)
                    extra_attr_obj = parse_obj_as(List[cls], extra_attr_dict)
                    update_links(new_doc, extra_attr_obj)
                elif extra_type == 'dict':
                    if extra_attr_dict:
                        cls = getattr(import_module(module_name), class_name)                        
                        keys = list(extra_attr_dict.keys())
                        key_type = type(keys[0])
                        extra_attr_obj = parse_obj_as(Dict[key_type, cls], extra_attr_dict)
                        update_links(new_doc, list(extra_attr_obj.values()))
                elif extra_type == 'noparse':
                    continue
                else:
                    raise NotImplementedError(f'Unknown type: {extra_type}')

                setattr(page, extra_field, extra_attr_obj)
        return new_doc

    @property
    def doc(self):
        return self

    # TODO proper path processing please...
    def _splitPath(self, path):
        page_idx, word_idx = path.split(".", 1)
        return (int(page_idx[2:]), int(word_idx[2:]))

    def get_word(self, jpath):
        page_idx, word_idx = self._splitPath(jpath)
        return self.pages[page_idx].words[word_idx]

    def get_page(self, jpath):
        page_idx, word_idx = self._splitPath(jpath)
        return self.pages[page_idx]

    def edit(self, edits):
        def clearWord(doc, path):
            word = doc.get_word(path)
            word.clear()
            return word

        def clearChar(doc, path, clearChar):
            word = doc.get_word(path)
            for char in clearChar:
                word.clear(char)
            return word

        def newWord(doc, text, xpath, ypath):
            xword = doc.get_word(xpath)
            yword = doc.get_word(ypath)
            page = doc.get_page(xpath)

            box = Shape.build_box([xword.xmin, yword.ymin, xword.xmax, yword.ymax])
            word = page.add_word(text, box)
            return word

        def replaceStr(doc, path, old, new):
            word = doc.get_word(path)
            word.replaceStr(old, new)
            return word

        for edit in edits:
            #print(f"Edit: {edit}")
            editList = shlex.split(edit.strip())
            proc = editList.pop(0)
            cmd = locals()[proc]
            cmd(self, *editList)
