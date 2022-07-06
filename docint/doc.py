from dataclasses import dataclass
from importlib import import_module
import subprocess
from typing import List, Tuple, Dict, Any
import math
from base64 import b64encode

from pydantic import BaseModel, Field, parse_obj_as

from pathlib import Path
import json
import shlex

import pdfplumber
import pdf2image
import pydantic
import msgpack
from wand.image import Image

from .shape import Shape, Box, Coord
from .page import Page
from .region import Region


# A container for tracking the document from a pdf/image to extracted information.

class PageImage(BaseModel):
    image_width: float
    image_height: float
    image_path: str
    image_box: Box
    image_type: str
    page: Page = None # A better solution is to save page_width, page_height ## TODO
    wimage: Any = None
    transformations: List[Tuple] = []

    class Config:
        fields = {'page': {'exclude': True},
                  'wimage': {'exclude': True},
                  'transformations': {'exclude': True}}

    def transform_rotate(self, image_coord, angle, prev_size, curr_size):
        angle_rad = math.radians(-1 * angle)

        prev_width, prev_height = prev_size
        curr_width, curr_height = curr_size

        image_x_centre, image_y_centre = prev_width/2.0, prev_height/2.0
        centre_x = image_coord.x - prev_width + image_x_centre
        centre_y = prev_height - image_coord.y - image_y_centre

        rota_centre_x = (centre_x * math.cos(angle_rad)) - (centre_y * math.sin(angle_rad))
        rota_centre_y = (centre_y * math.cos(angle_rad)) + (centre_x * math.sin(angle_rad))

        rota_image_x, rota_image_y = rota_centre_x + curr_width/2, curr_height/2 - rota_centre_y

        rota_image_x = min(max(0, rota_image_x), curr_width)
        rota_image_y = min(max(0, rota_image_y), curr_height)
        image_coord = Coord(x=round(rota_image_x), y=round(rota_image_y))
        return image_coord

    def transform(self, image_coord):
        for trans_tuple in self.transformations:
            if trans_tuple[0] == 'crop':
                top, bot = trans_tuple[1], trans_tuple[2]
                if not image_coord.inside(top, bot):
                    assert False, f'coord: {image_coord} outside [{cur_w}, {cur_h}]'
                    raise ValueError(f'coord: {image_coord} outside crop_area [{top}, {bot}]')
                image_coord = Coord(x=image_coord.x - top.x, y=image_coord.y - top.y)
            elif trans_tuple[0] == 'rotate':
                angle, prev_size, curr_size = trans_tuple[1], trans_tuple[2], trans_tuple[3]
                image_coord = self.transform_rotate(image_coord, angle, prev_size, curr_size)
        return image_coord


    def inverse_transform(self, image_coord):
        #print(f'\t>inverse_transform image_coord: {image_coord}')
        for trans_tuple in reversed(self.transformations):
            if trans_tuple[0] == 'crop':
                top, bot = trans_tuple[1], trans_tuple[2]
                cur_w, cur_h = (bot.x - top.x), (bot.y - top.y)
                if not image_coord.inside(Coord(x=0, y=0), Coord(x=cur_w, y=cur_h)):
                    assert False, f'coord: {image_coord} outside [{cur_w}, {cur_h}]'
                    raise ValueError(f'coord: {image_coord} outside [{cur_w}, {cur_h}]')
                image_coord = Coord(x=top.x + image_coord.x, y=top.y + image_coord.y)
                #print(f'\t>inverse_crop image_coord: {image_coord}')
            else:
                angle, prev_size, curr_size = trans_tuple[1], trans_tuple[2], trans_tuple[3]
                image_coord = self.transform_rotate(image_coord, -angle, curr_size, prev_size)
                #print(f'\t>inverse_rotate image_coord: {image_coord}')
        return image_coord

    def get_image_coord(self, doc_coord):
        page_x = round(doc_coord.x * self.page.width)
        page_y = round(doc_coord.y * self.page.height)

        image_x_scale = self.image_width / (self.image_box.bot.x - self.image_box.top.x)
        image_y_scale = self.image_height / (self.image_box.bot.y - self.image_box.top.y)

        image_x = round((page_x - self.image_box.top.x) * image_x_scale)
        image_y = round((page_y - self.image_box.top.y) * image_y_scale)

        image_x = min(max(0, image_x), self.image_width)
        image_y = min(max(0, image_y), self.image_height)

        image_coord = self.transform(Coord(x=image_x, y=image_y))
        return image_coord


    def get_doc_coord(self, image_coord):
        #print(f'>get_doc_coord image_coord: {image_coord}')
        image_coord = self.inverse_transform(image_coord)
        #print(f'>after_inv_trans image_coord: {image_coord}')

        page_x_scale = (self.image_box.bot.x - self.image_box.top.x)/self.image_width
        page_y_scale = (self.image_box.bot.y - self.image_box.top.y)/self.image_height

        page_x, page_y = image_coord.x * page_x_scale, image_coord.y * page_y_scale
        ### ADDED THIS LATER <<< 
        page_x, page_y = page_x + self.image_box.top.x, page_y + self.image_box.top.y
        doc_coord = Coord(x=page_x/self.page.width, y=page_y/self.page.height)
        return doc_coord

    def _init_image(self):
        if self.wimage is None:
            image_path = self.page.doc.get_image_path(self.page.page_idx)
            self.wimage = Image(filename=image_path)

    def get_skew_angle(self, orientation):
        self._init_image()
        if orientation == 'h':
            hor_image = self.wimage.clone()
            hor_image.deskew(0.8 * self.wimage.quantum_range)
            angle = float(hor_image.artifacts['deskew:angle'])
        else:
            ver_image = self.wimage.clone()
            ver_image.rotate(90)
            ver_image.deskew(0.8 * ver_image.quantum_range)
            angle = float(ver_image.artifacts['deskew:angle'])
        return angle

    def rotate(self, angle, background='white'):
        if not self.wimage:
            self._init_image()

        prev_size = (self.wimage.width, self.wimage.height)
        self.wimage.rotate(angle, background=background)
        curr_size = (self.wimage.width, self.wimage.height)
        #print(f'\tRotate prev_size: {prev_size} curr_size: {curr_size} angle: {angle}')
        self.transformations.append(('rotate', angle, prev_size, curr_size))

    def crop(self, top, bot):
        if not self.wimage:
            self._init_image()
        img_top, img_bot = self.get_image_coord(top), self.get_image_coord(bot)
        self.wimage.crop(left=round(img_top.x), top=round(img_top.y),
                         right=round(img_bot.x), bottom=round(img_bot.y))

        #print(f'\tCrop top: {top} bot: {bot} img_top: {img_top} img_bot: {img_bot}')
        self.transformations.append(('crop', img_top, img_bot))

        # todo rotate

    def get_base64_image(self, top, bot, format='png', height=50):
        if not self.wimage:
            self._init_image()

        img_top, img_bot = self.get_image_coord(top), self.get_image_coord(bot)
        with self.wimage[int(img_top.x):int(img_bot.x), int(img_top.y):int(img_bot.y)] as cropped:
            if height:
                cw, ch = cropped.size
                width = int((cw * height)/ch)
                cropped.resize(width=width, height=height)

            img_bin = cropped.make_blob(format)
            img_str = f"data:image/{format};base64," + b64encode(img_bin).decode()
        return img_str

    def clear_transforms(self):
        if self.wimage:
            self.wimage.destroy()
            self.wimage = None
        self.transformations.clear()

    @property
    def curr_size(self):
        if self.wimage is not None:
            return self.wimage.width, self.wimage.height
        else:
            return self.image_width, self.image_height



class PageInfo(BaseModel):
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
    _image_root: str = None

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
        image_dir = Path(self._image_root) / self.pdf_stem
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
            doc.page_infos.append(PageInfo(width=page.width, height=page.height, num_images=len(page.images)))

            # TODO: check the shape of page image and extract only if it covers full page
            if len(page.images) == 1:
                img = page.images[0]
                width, height = tuple(map(int, img["srcsize"]))
                x0, y0, x1, y1 = img["x0"], img["y0"], img["x1"], img["y1"]

                if img["top"] != y0 or img["bottom"] != y1:
                    print('Warning: misaligned image_box')
                    y0, y1 = img["top"], img["bottom"]

                top, bot = Coord(x=x0, y=y0), Coord(x=x1, y=y1)

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
            page_image = PageImage(image_width=width, image_height=height, image_path=image_path, image_box=image_box, image_type=image_type)
            doc.page_images.append(page_image)
        # end
        pdf_info = {"page_infos": doc.page_infos, "page_images": doc.page_images}
        pdf_info_path.write_text(
            json.dumps(pdf_info, default=pydantic.json.pydantic_encoder, indent=2)
        )
        return doc

    def to_json(self):
        return self.json(exclude_defaults=True) # removed indent, models_as_dict=False

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

        def update_region_links(doc, region):
            region.words = [doc[region.page_idx_][idx] for idx in region.word_idxs]
            if region.word_lines_idxs:
                p_idx, wl_idxs = region.page_idx_, region.word_lines_idxs
                region.word_lines = [[doc[p_idx][idx] for idx in wl] for wl in wl_idxs]

        def update_links(doc, regions):
            if regions and not isinstance(regions[0], Region):
                return
            inner_regions = [ ir for r in regions for ir in r.get_regions() ]
            for region in inner_regions:
                    update_region_links(doc, region)

        json_file = Path(json_file)
        if json_file.suffix.lower() in ('.json', '.jsn'):
            doc_dict = json.loads(json_file.read_text())
        else:
            doc_dict = msgpack.unpackb(json_file.read_bytes())
        new_doc = Doc(**doc_dict)

        # need to supply the field_set, page has 'doc' field excluded
        #new_doc = Doc.construct(**doc_dict)

        # link doc to page and words
        for page in new_doc.pages:
            page.doc = new_doc
            for word in page.words:
                word.doc = new_doc

        for extra_field, field_tuple in new_doc.extra_fields.items():
            extra_attr_dict = getattr(new_doc, extra_field, None)
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

            # overwrite the attribute with new object
            setattr(new_doc, extra_field, extra_attr_obj)

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

                # overwrite the attribute with new object
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

    def get_words(self, jpath):
        def split_path(idx):
            idx = idx[2:]
            print(idx)
            s, e = idx.split(':') if ':' in idx else (int(idx), int(idx) + 1)
            return (int(s), int(e))

        if ':' not in jpath:
            return [self.get_word(jpath)]

        words = []
        page_path, word_path = jpath.split(".", 1)
        for p_idx in range(*split_path(page_path)):
            for w_idx in range(*split_path(word_path)):
                words.append(self.pages[p_idx].words[w_idx])
        return words

    def get_page(self, jpath):
        page_idx, word_idx = self._splitPath(jpath)
        return self.pages[page_idx]

    def get_region(self, region_path):
        item = self
        name_dict = {'pa': 'pages', 'wo': 'words', 'ta': 'tables', 'ro': 'body_rows', 'ce': 'cells', 'li': 'list_items' }
        for item_path in region_path.split('.'):
            if item_path[-1].isdigit():
                name = item_path.strip('0123456789')
                idx = int(item_path[len(name):])
                name = name_dict.get(name, name)
                item = getattr(item, name)[idx]
            else:
                name = name_dict.get(item_path, item_path)
                item = item.get(name) if isinstance(item, dict) else getattr(item, name)
        return item

    def get_edge(self, jpath):
        (page_idx, table_idx, edge_idx) = [int(e[2:]) for e in jpath.split(".")]

        if '.ro' in jpath:
            return self.pages[page_idx].table_edges_list[table_idx].row_edges[edge_idx]
        else:
            return self.pages[page_idx].table_edges_list[table_idx].col_edges[edge_idx]

    def get_edge_paths(self, jpath):
        edge_idxs = jpath.split(".")[-1][2:]
        if ':' in edge_idxs:
            start, end = (int(idx) for idx in edge_idxs.split(':'))
            assert end > start
            stub = jpath[:-len(edge_idxs)]
            return [f'{stub}{idx}' for idx in range(start, end)]
        else:
            return jpath

    def edit(self, edits):
        def clearWord(doc, path):
            word = doc.get_word(path)
            word.clear()
            return word

        def clearWords(doc, *paths):
            return [clearWord(doc, path) for path in paths]


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

        def mergeWords(doc, *paths):
            assert len(paths) > 1
            to_merge_words = [doc.get_word(p) for p in paths[1:]]
            to_merge_text = ''.join(w.text for w in to_merge_words)

            main_word = doc.get_word(paths[0])
            new_text = main_word.text + to_merge_text

            main_word.replaceStr('<all>', new_text)
            [w.replaceStr('<all>', '') for w in to_merge_words]


        def splitWord(doc, path, split_str):
            word = doc.get_word(path)
            box = word.box
            
            assert split_str in word.text
            split_idx = word.text.index(split_str) + len(split_str)
            
            lt_str = word.text[:split_idx]
            rt_str = word.text[split_idx:]

            print(f'Left: {lt_str} Right: {rt_str}')

            split_x = box.xmin + (box.width * len(lt_str)/len(word.text))
            
            word.replaceStr('<all>', lt_str)
            lt_box = Shape.build_box([box.top.x, box.top.y, split_x, box.bot.y])
            word.shape_ = lt_box
            
            rt_box = Shape.build_box([split_x, box.top.y, box.bot.x, box.bot.y])
            rt_word = word.page.add_word(rt_str, rt_box)
            return word
        
        def replaceStr(doc, path, old, new):
            word = doc.get_word(path)
            word.replaceStr(old, new)
            return word

        def moveEdge(doc, path, coord_idx, direction, num_thou=5):
            edge = doc.get_edge(path)
            idx = int(coord_idx[1])
            offset = int(num_thou) * 0.001
            assert idx in (1, 2)
            move_coord = getattr(edge, f'coord{idx}')
            if direction == 'up':
                move_coord.y -= offset
            elif direction == 'down':
                move_coord.y += offset
            elif direction == 'left':
                move_coord.x -= offset
            else:
                move_coord.x += offset
            return edge

        def moveEdges(doc, path, coord, direction, num_thou=5):
            edge_paths = doc.get_edge_paths(path)
            return [moveEdge(doc, p, coord, direction, num_thou) for p in edge_paths]

        def addWords(doc, region_path, *word_paths):
            region = doc.get_region(region_path)
            add_words = [ doc.get_word(p) for p in word_paths ]
            region.words += add_words
            #region.text_ = None
            region.shape_ = None
            return region
        
        # def newRegionToList(doc, parent_path, *word_paths):
        #     parent = doc.get_region(parent_path)
        #     assert word_paths
        #     add_words = [ doc.get_word(p) for p in word_paths ]
        #     new_region = Region.build(add_words, add_words[0].page_idx)
        #     assert isinstance(parent, list)
        #     parent.append(new_region)
        #     return new_region

        # def newRegion(doc, parent_path, region_name, *word_paths):
        #     parent = doc.get_region(parent_path)
        #     assert word_paths
        #     add_words = [ doc.get_word(p) for p in word_paths ]
        #     new_region = Region.build(add_words, add_words[0].page_idx)
        #     assert isinstance(parent, list)
        #     parent.append(new_region)
        #     return new_region

        def deletePage(doc, path):
            del_idx = int(path[2:])
            assert del_idx < len(doc.pages)

            doc.pages.pop(del_idx)
            doc.page_images.pop(del_idx)
            doc.page_infos.pop(del_idx)

            for page in doc.pages[del_idx:]:
                page.page_idx -= 1


        for edit in edits:
            #print(f"Edit: {edit}")
            editList = shlex.split(edit.strip())
            proc = editList.pop(0)
            cmd = locals()[proc]
            cmd(self, *editList)
