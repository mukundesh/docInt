import json
import shlex
import shutil
from importlib import import_module
from itertools import zip_longest
from pathlib import Path
from typing import Dict, List, Tuple

import pydantic
from more_itertools import flatten
from pydantic import BaseModel, parse_obj_as

from . import pdfwrapper
from .errors import Errors
from .page import Page
from .page_image import PageImage
from .region import Region
from .shape import Box, Coord, Shape

# A container for tracking the document from a pdf/image to extracted information.


class PageInfo(BaseModel):
    width: float
    height: float
    num_images: int


class Doc(BaseModel):
    pdffile_path: Path
    pages: List[Page] = []  # field(default_factory=list)
    page_infos: List[PageInfo] = []  # field(default_factory=list)
    page_images: List[PageImage] = []  # field(default_factory=list)
    extra_fields: Dict[str, Tuple] = {}
    extra_page_fields: Dict[str, Tuple] = {}
    _image_root: str = None

    class Config:
        extra = "allow"

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
        angle = getattr(self.pages[page_idx], "reoriented_angle", 0)
        if angle != 0:
            return image_dir / f"orig-{page_num:03d}-000-r{angle}.png"
        else:
            return image_dir / f"orig-{page_num:03d}-000.png"

    # move this to document factory
    @classmethod
    def build_doc(cls, pdf_path, image_dirs_path):
        def get_image_path(pdf_path, image_dirs_path, page_idx):
            image_dirs_path = cls.image_dirs_path if not image_dirs_path else image_dirs_path
            image_name = f"orig-{page_idx+1:03d}-000.png"
            image_path = Path(image_dirs_path) / pdf_path.name[:-4] / Path(image_name)
            return image_path

        doc = Doc(pdffile_path=pdf_path)
        image_dirs_path = cls.image_dirs_path if not image_dirs_path else image_dirs_path
        image_dir_path = Path(image_dirs_path) / pdf_path.name[:-4]
        pdf_info_path = image_dir_path / (doc.pdf_name + ".pdfinfo.json")

        if image_dir_path.exists() and pdf_info_path.exists():
            pdf_info = json.loads(pdf_info_path.read_text())
            doc.page_infos = [PageInfo(**p) for p in pdf_info["page_infos"]]
            doc.page_images = [PageImage(**i) for i in pdf_info["page_images"]]
            return doc

        image_dir_path.mkdir(exist_ok=True, parents=True)
        pdf = pdfwrapper.open(pdf_path, library_name="pypdfium2")
        for (page_idx, page) in enumerate(pdf.pages):
            doc.page_infos.append(PageInfo(width=page.width, height=page.height, num_images=len(page.images)))

            image_path = get_image_path(pdf_path, image_dirs_path, page_idx)
            if page.has_one_large_image:
                image = page.images[0]
                width, height = image.width, image.height
                x0, y0, x1, y1 = image.bounding_box
                top, bot = Coord(x=x0, y=y0), Coord(x=x1, y=y1)
                image_box = Box(top=top, bot=bot)
                image_type = "original"
                image.save(image_path)
            else:
                width, height = page.page_image_save(image_path)
                print("Raster**:", width, height)
                [x0, y0, x1, y1] = [0, 0, page.width, page.height]
                top, bot = Coord(x=x0, y=y0), Coord(x=x1, y=y1)
                image_box = Box(top=top, bot=bot)
                image_type = "raster"

            page_image = PageImage(
                image_width=width,
                image_height=height,
                image_path=str(image_path),
                image_box=image_box,
                image_type=image_type,
                page_width=page.width,
                page_height=page.height,
            )
            doc.page_images.append(page_image)
        # end
        pdf_info = {"page_infos": doc.page_infos, "page_images": doc.page_images}
        pdf_info_path.write_text(json.dumps(pdf_info, default=pydantic.json.pydantic_encoder, indent=2))
        return doc

    def to_json(self):
        return self.json(exclude_defaults=True)  # removed indent, models_as_dict=False

    def to_disk(self, disk_file, format="json"):
        disk_file = Path(disk_file)
        if format == "json":
            disk_file.write_text(self.to_json())
        else:
            raise NotImplementedError(f"Unknown format: {format}")
            # disk_file.write_bytes(self.to_msgpack())

    def copy_pdf(self, file_path):
        file_path = Path(file_path)
        shutil.copy(self.pdf_path, file_path)

    def add_extra_page_field(self, field_name, field_tuple):
        self.extra_page_fields[field_name] = field_tuple

    def add_extra_field(self, field_name, field_tuple):
        self.extra_fields[field_name] = field_tuple

    @classmethod  # noqa C901
    def from_dict(cls, doc_dict):  # noqa C901
        def get_extra_fields(obj):
            all_fields = set(obj.dict().keys())
            def_fields = set(obj.__fields__.keys())
            return all_fields.difference(def_fields)

        # should call post_init
        def update_region_links(doc, region):
            region.words = [doc[region.page_idx_][idx] for idx in region.word_idxs]
            if hasattr(region, "word_lines_idxs") and region.word_lines_idxs is not None:
                p_idx, wl_idxs = region.page_idx_, region.word_lines_idxs
                region.word_lines = [[doc[p_idx][idx] for idx in wl] for wl in wl_idxs]

        def update_links(doc, regions):
            if regions and not isinstance(regions[0], Region):
                return
            inner_regions = [ir for r in regions for ir in r.get_regions()]
            for region in inner_regions:
                update_region_links(doc, region)

        new_doc = Doc(**doc_dict)
        # need to supply the field_set, page has 'doc' field excluded
        # new_doc = Doc.construct(**doc_dict)

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
            # TODO
            module_name = module_name.replace("docint.extracts", "orgpedia.extracts")

            if extra_type == "obj":
                cls = getattr(import_module(module_name), class_name)
                extra_attr_obj = parse_obj_as(cls, extra_attr_dict)
                update_links(new_doc, [extra_attr_obj])
            elif extra_type == "list":
                cls = getattr(import_module(module_name), class_name)
                extra_attr_obj = parse_obj_as(List[cls], extra_attr_dict)
                update_links(new_doc, extra_attr_obj)
            elif extra_type == "dict":
                if extra_attr_dict:
                    cls = getattr(import_module(module_name), class_name)
                    keys = list(extra_attr_dict.keys())
                    key_type = type(keys[0])
                    extra_attr_obj = parse_obj_as(Dict[key_type, cls], extra_attr_dict)
                    update_links(new_doc, list(extra_attr_obj.values()))
            elif extra_type == "dict_list":
                if extra_attr_dict:
                    cls = getattr(import_module(module_name), class_name)
                    keys = list(extra_attr_dict.keys())
                    key_type = type(keys[0])
                    extra_attr_obj = parse_obj_as(Dict[key_type, List[cls]], extra_attr_dict)
                    update_links(new_doc, list(flatten(extra_attr_obj.values())))
            elif extra_type == "noparse":
                continue
            else:
                raise NotImplementedError(f"Unknown type: {extra_type}")

            # overwrite the attribute with new object
            setattr(new_doc, extra_field, extra_attr_obj)

        for page in new_doc.pages:
            for extra_field, field_tuple in new_doc.extra_page_fields.items():
                extra_attr_dict = getattr(page, extra_field, None)
                if not extra_attr_dict:
                    continue
                (extra_type, module_name, class_name) = field_tuple

                # TODO
                module_name = module_name.replace("docint.extracts", "orgpedia.extracts")
                if extra_type == "obj":
                    cls = getattr(import_module(module_name), class_name)
                    extra_attr_obj = parse_obj_as(cls, extra_attr_dict)
                    update_links(new_doc, [extra_attr_obj])
                elif extra_type == "list":
                    cls = getattr(import_module(module_name), class_name)
                    extra_attr_obj = parse_obj_as(List[cls], extra_attr_dict)
                    update_links(new_doc, extra_attr_obj)
                elif extra_type == "dict":
                    if extra_attr_dict:
                        cls = getattr(import_module(module_name), class_name)
                        keys = list(extra_attr_dict.keys())
                        key_type = type(keys[0])
                        extra_attr_obj = parse_obj_as(Dict[key_type, cls], extra_attr_dict)
                        update_links(new_doc, list(extra_attr_obj.values()))
                elif extra_type == "dict_list":
                    if extra_attr_dict:
                        cls = getattr(import_module(module_name), class_name)
                        keys = list(extra_attr_dict.keys())
                        key_type = type(keys[0])
                        extra_attr_obj = parse_obj_as(Dict[key_type, List[cls]], extra_attr_dict)
                        update_links(new_doc, list(flatten(extra_attr_obj.values())))
                elif extra_type == "noparse":
                    continue
                else:
                    raise NotImplementedError(f"Unknown type: {extra_type}")

                # overwrite the attribute with new object
                setattr(page, extra_field, extra_attr_obj)
        return new_doc

    @classmethod  # noqa: C901
    def from_disk(cls, json_file):  # noqa: C901
        json_file = Path(json_file)
        if json_file.suffix.lower() in (".json", ".jsn"):
            doc_dict = json.loads(json_file.read_text())
        else:
            # doc_dict = msgpack.unpackb(json_file.read_bytes())
            NotImplementedError(f"Unknown suffix: {json_file.suffix}")
        return Doc.from_dict(doc_dict)

    @property
    def doc(self):
        return self

    # TODO proper path processing please...
    # combine all of these in one single path
    def _splitPath(self, path):
        page_idx, word_idx = path.split(".", 1)
        return (int(page_idx[2:]), int(word_idx[2:]))

    def get_word(self, jpath):
        page_idx, word_idx = self._splitPath(jpath)
        return self.pages[page_idx].words[word_idx]

    def get_words(self, jpath):
        def split_path(idx):
            idx = idx[2:]
            s, e = idx.split(":") if ":" in idx else (int(idx), int(idx) + 1)
            return (int(s), int(e))

        if ":" not in jpath:
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
        name_dict = {
            "pa": "pages",
            "wo": "words",
            "ta": "tables",
            "ro": "body_rows",
            "ce": "cells",
            "li": "list_items",
        }
        for item_path in region_path.split("."):
            if item_path[-1].isdigit():
                name = item_path.strip("0123456789")
                idx = int(item_path[len(name) :])  # noqa: E203
                name = name_dict.get(name, name)
                item = getattr(item, name)[idx]
            else:
                name = name_dict.get(item_path, item_path)
                item = item.get(name) if isinstance(item, dict) else getattr(item, name)
        return item

    def get_edge(self, jpath):
        (page_idx, table_idx, edge_idx) = [int(e[2:]) for e in jpath.split(".")]

        if ".ro" in jpath:
            return self.pages[page_idx].table_edges_list[table_idx].row_edges[edge_idx]
        else:
            return self.pages[page_idx].table_edges_list[table_idx].col_edges[edge_idx]

    def get_edge_paths(self, jpath):
        edge_idxs = jpath.split(".")[-1][2:]
        if ":" in edge_idxs:
            start, end = (int(idx) for idx in edge_idxs.split(":"))
            assert end > start
            stub = jpath[: -len(edge_idxs)]
            return [f"{stub}{idx}" for idx in range(start, end)]
        else:
            return jpath

    def edit(self, edits, file_path="", line_nums=[]):  # noqa: C901
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

        def newAdjWord(doc, text, path, direction="left"):
            word = doc.get_word(path)
            page = doc.get_page(path)

            assert direction in ("left", "right")
            assert len(word), "the word given does not have any text"

            word_width = word.xmax - word.xmin
            char_width = word_width / len(word)
            new_word_width = char_width * len(text)

            if direction == "left":
                xmax = word.xmin - 0.02
                xmin = xmax - new_word_width
            else:
                xmin = word.xmax + 0.02
                xmax = xmin + new_word_width

            print(f"Word: {word.xmin} - {word.xmax} New: {xmin}-{xmax}")

            box = Shape.build_box([xmin, word.ymin, xmax, word.ymax])
            new_word = page.add_word(text, box)
            return new_word

        def mergeWords(doc, *paths):
            assert len(paths) > 1
            to_merge_words = [doc.get_word(p) for p in paths[1:]]
            to_merge_text = "".join(w.text for w in to_merge_words)

            main_word = doc.get_word(paths[0])
            new_text = main_word.text + to_merge_text

            main_word.replaceStr("<all>", new_text)
            [w.replaceStr("<all>", "") for w in to_merge_words]

        def splitWord(doc, path, split_str):
            word = doc.get_word(path)
            box = word.box

            assert split_str in word.text
            split_idx = word.text.index(split_str) + len(split_str)

            lt_str = word.text[:split_idx]
            rt_str = word.text[split_idx:]

            print(f"Left: {lt_str} Right: {rt_str}")

            split_x = box.xmin + (box.width * len(lt_str) / len(word.text))

            word.replaceStr("<all>", lt_str)
            lt_box = Shape.build_box([box.top.x, box.top.y, split_x, box.bot.y])
            word.shape_ = lt_box

            rt_box = Shape.build_box([split_x, box.top.y, box.bot.x, box.bot.y])
            word.page.add_word(rt_str, rt_box)
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
            move_coord = getattr(edge, f"coord{idx}")
            if direction == "up":
                move_coord.y -= offset
            elif direction == "down":
                move_coord.y += offset
            elif direction == "left":
                move_coord.x -= offset
            else:
                move_coord.x += offset
            return edge

        def moveEdges(doc, path, coord, direction, num_thou=5):
            edge_paths = doc.get_edge_paths(path)
            return [moveEdge(doc, p, coord, direction, num_thou) for p in edge_paths]

        def addWords(doc, region_path, *word_paths):
            region = doc.get_region(region_path)
            add_words = [doc.get_word(p) for p in word_paths]
            region.words += add_words
            # region.text_ = None
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

        if line_nums:
            assert len(line_nums) == len(edits)

        for (edit, line_num) in zip_longest(edits, line_nums, fillvalue=""):
            # print(f"Edit: {edit}")
            editList = shlex.split(edit.strip())
            proc = editList.pop(0)

            cmd = locals().get(proc, None)
            if not cmd:
                file_str = str(file_path)
                line_str = f"{file_str}:{line_num}" if (file_path or line_num) else ""
                raise ValueError(Errors.E020.format(line_num=line_str, function=proc))

            cmd(self, *editList)
