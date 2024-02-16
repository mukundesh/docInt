import gzip
import json
import shlex
import shutil
from enum import IntEnum
from importlib import import_module
from itertools import zip_longest
from pathlib import Path
from typing import Any, Dict, List

from more_itertools import flatten
from pydantic import BaseModel, parse_obj_as

from . import pdfwrapper
from .data_edit import DataEdit
from .data_error import DataError
from .errors import Errors
from .page import Page
from .region import Region
from .shape import Shape

# A container for tracking the document from a pdf/image to extracted information.


class ExtractType(IntEnum):
    BaseType = 0
    Object = 1
    List = 2
    Dict = 3
    DictList = 4


class ExtractInfo(BaseModel):
    field_name: str
    field_type: ExtractType
    module_name: str
    class_name: str
    pipe_name: str

    def get_class(self):
        if self.module_name and self.class_name:
            return getattr(import_module(self.module_name), self.class_name)
        else:
            return None

    def get_objects(self, extract):
        if self.field_type in (ExtractType.BaseType, ExtractType.Object):
            return [extract]
        elif self.field_type == ExtractType.List:
            return extract
        elif self.field_type == ExtractType.Dict:
            return list(extract.values())
        elif self.field_type == ExtractType.DictList:
            return list(flatten(extract.values()))
        else:
            raise NotImplementedError(f"Unknown type: {self.field_type}")


class Doc(BaseModel):
    pdffile_path: Path
    pages: List[Page] = []  # field(default_factory=list)

    doc_extract_infos: Dict[str, ExtractInfo] = {}
    page_extract_infos: Dict[str, ExtractInfo] = {}

    pipe_names: List[str] = []
    errors: Dict[str, List[DataError]] = {}
    edits: Dict[str, List[DataEdit]] = {}
    config: Dict[str, Dict[str, Any]] = {}

    class Config:
        extra = "allow"

    def __getitem__(self, idx):
        if isinstance(idx, slice) or isinstance(idx, int):
            return self.pages[idx]
        else:
            raise TypeError(f"Unknown type {idx} {type(idx)} this method can handle")

    @property
    def num_pages(self):
        return len(self.pages)

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
    def file_name(self):
        return self.pdf_name

    # move this to document factory
    @classmethod
    def build_doc(cls, pdf_path):
        doc = Doc(pdffile_path=pdf_path)
        pdf = pdfwrapper.open(pdf_path)
        for page_idx, pdf_page in enumerate(pdf.pages):
            page = Page(
                doc=doc,
                page_idx=page_idx,
                words=[],
                width_=pdf_page.width,
                height_=pdf_page.height,
            )
            doc.pages.append(page)
        return doc

    def to_json(self, exclude_defaults=True):
        return self.json(exclude_defaults=exclude_defaults, sort_keys=True, separators=(",", ":"))

    def to_dict(self, exclude_defaults=True):
        return self.dict(exclude_defaults=exclude_defaults)

    def to_disk(self, disk_file, format="json", exclude_defaults=True):
        disk_file = Path(disk_file)
        if format == "json":
            if disk_file.suffix.lower() in (".gz"):
                with gzip.open(disk_file, "wb") as f:
                    f.write(
                        bytes(self.to_json(exclude_defaults=exclude_defaults), encoding="utf-8")
                    )
            else:
                disk_file.write_text(self.to_json(exclude_defaults=exclude_defaults))
        else:
            raise NotImplementedError(f"Unknown format: {format}")
            # disk_file.write_bytes(self.to_msgpack())

    def copy_pdf(self, file_path):
        file_path = Path(file_path)
        shutil.copy(self.pdf_path, file_path)

    def add_doc_extract(self, field_name, field_type, module_name, class_name):
        extract_info = ExtractInfo(
            field_name=field_name,
            field_type=field_type,
            module_name=module_name,
            class_name=class_name,
            pipe_name=self.pipe_names[-1],
        )
        self.doc_extract_infos[field_name] = extract_info

    def add_page_extract(self, field_name, field_type, module_name, class_name):
        extract_info = ExtractInfo(
            field_name=field_name,
            field_type=field_type,
            module_name=module_name,
            class_name=class_name,
            pipe_name=self.pipe_names[-1],
        )
        self.page_extract_infos[field_name] = extract_info

    def has_page_extract(self, field_name):
        return field_name in self.page_extract_infos

    def has_doc_extract(self, field_name):
        return field_name in self.doc_extract_infos

    def add_extra_page_field(self, field_name, field_tuple):
        (extra_type, module_name, class_name) = field_tuple
        field_type = {
            "noparse": ExtractType.BaseType,
            "obj": ExtractType.Object,
            "list": ExtractType.List,
            "dict": ExtractType.Dict,
            "dict_list": ExtractType.DictList,
        }[extra_type]

        self.add_page_extract(field_name, field_type, module_name, class_name)

    def add_extra_field(self, field_name, field_tuple):
        (extra_type, module_name, class_name) = field_tuple
        field_type = {
            "noparse": ExtractType.BaseType,
            "obj": ExtractType.Object,
            "list": ExtractType.List,
            "dict": ExtractType.Dict,
            "dict_list": ExtractType.DictList,
        }[extra_type]

        self.add_doc_extract(field_name, field_type, module_name, class_name)

    def remove_extra_field(self, field_name):
        del self.doc_extract_infos[field_name]

        if hasattr(self, field_name):
            delattr(self, field_name)

    def remove_extra_page_field(self, field_name):
        del self.page_extract_infos[field_name]

        for page in self.pages:
            if hasattr(page, field_name):
                delattr(page, field_name)

    def remove_all_extra_fields(self, except_fields=[]):
        doc_fields = [f for f in self.doc_extract_infos if f not in except_fields]
        for field_name in doc_fields:
            self.remove_extra_field(field_name)

        page_fields = [f for f in self.page_extract_infos if f not in except_fields]
        for field_name in page_fields:
            self.remove_extra_page_field(field_name)

    @classmethod  # noqa C901
    def from_dict(cls, doc_dict):  # noqa C901
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

        def build_extract(obj, extract_info):
            # print(f'Extracting: {extract_info.field_name}')
            extract_dict = getattr(obj, extract_info.field_name, None)
            if not extract_dict:
                return

            cls = extract_info.get_class()

            if extract_info.field_type == ExtractType.BaseType:
                return

            elif extract_info.field_type == ExtractType.Object:
                extract = parse_obj_as(cls, extract_dict)
                update_links(obj.doc, [extract])

            elif extract_info.field_type == ExtractType.List:
                extract = parse_obj_as(List[cls], extract_dict)
                update_links(obj.doc, extract)

            elif extract_info.field_type == ExtractType.Dict:
                key_type = type(list(extract_dict.keys())[0])
                extract = parse_obj_as(Dict[key_type, cls], extract_dict)
                update_links(obj.doc, list(extract.values()))

            elif extract_info.field_type == ExtractType.DictList:
                key_type = type(list(extract_dict.keys())[0])
                extract = parse_obj_as(Dict[key_type, List[cls]], extract_dict)
                update_links(obj.doc, list(flatten(extract.values())))
            else:
                raise NotImplementedError(f"Unknown type: {extract_info.field_type}")

            setattr(obj, extract_info.field_name, extract)

        # TODO use construct to speed up the document loading
        # need to supply the field_set, page has 'doc' field excluded
        # new_doc = Doc.construct(**doc_dict)

        new_doc = Doc(**doc_dict)
        # link doc to page and words
        for page in new_doc.pages:
            page.doc = new_doc
            for word in page.words:
                word.doc = new_doc

        for extract_info in new_doc.doc_extract_infos.values():
            build_extract(new_doc, extract_info)

        for page in new_doc.pages:
            for extract_info in new_doc.page_extract_infos.values():
                build_extract(page, extract_info)
        return new_doc

    @classmethod  # noqa: C901
    def from_disk(cls, json_file):  # noqa: C901
        json_file = Path(json_file)
        if json_file.suffix.lower() in (".json", ".jsn"):
            doc_dict = json.loads(json_file.read_text())
        elif json_file.suffix.lower() in (".gz"):
            with gzip.open(json_file, "rb") as f:
                doc_dict = json.loads(f.read())
        else:
            # doc_dict = msgpack.unpackb(json_file.read_bytes())
            NotImplementedError(f"Unknown suffix: {json_file.suffix}")
        return Doc.from_dict(doc_dict)

    @property
    def doc(self):
        return self

    def prepend_image_stub(self, stub):
        for page in self.pages:
            if page.page_image:
                page.page_image.prepend_image_stub(stub)

    def remove_image_stub(self, stub):
        for page in self.pages:
            if page.page_image:
                page.page_image.remove_image_stub(stub)

    def get_relevant_extracts(self, pipe, path, shape):
        relevant_extracts = {}

        def has_class_method(cls, method_name):
            method_attr = getattr(cls, method_name, None)
            return method_attr and callable(method_attr) and (method_attr.__self__ == cls)

        def add_relevant_extracts(doc_or_page, extract_info):
            field_name = extract_info.field_name
            extract = getattr(doc_or_page, field_name, None)
            if extract is None:
                return

            extract_object_class = extract_info.get_class()
            extract_objects = extract_info.get_objects(extract)

            if has_class_method(extract_object_class, "get_relevant_objects"):
                cls = extract_object_class
                relevant_objects = cls.get_relevant_objects(extract_objects, path, shape)
            else:
                relevant_objects = extract_objects
            relevant_extracts.setdefault(field_name, []).extend(relevant_objects)

        doc_eis = [e for e in self.doc_extract_infos.values() if e.pipe_name == pipe]
        for extract_info in doc_eis:
            add_relevant_extracts(self, extract_info)

        page = self.get_page(path)
        if not page:
            return None

        page_eis = [e for e in self.page_extract_infos.values() if e.pipe_name == pipe]
        for extract_info in page_eis:
            add_relevant_extracts(page, extract_info)

        return relevant_extracts

    def add_pipe(self, pipe_name):
        self.pipe_names.append(pipe_name)

    def add_errors(self, errors):
        pipe_name = self.pipe_names[-1]
        self.errors.setdefault(pipe_name, []).extend(errors)

    def add_edits(self, edits):
        pipe_name = self.pipe_names[-1]
        self.edits.setdefault(pipe_name, []).extend(edits)

    def get_pipe_html_lines(self, pipe_name):
        num_errors = len(self.errors.get(pipe_name, []))
        num_edits = len(self.edits.get(pipe_name, []))
        return [pipe_name, f"Errors: {num_errors} Edits: {num_edits}"]

    def get_errors(self, pipe_name):
        return self.errors.get(pipe_name, [])

    def get_edits(self, pipe_name):
        return self.edits.get(pipe_name, [])

    def add_config(self, pipe, config):
        pipe_name = self.pipe_names[-1]
        self.configs[pipe_name] = config

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
            return [jpath]

    def edit(self, edits, file_path="", line_nums=[]):  # noqa: C901
        def clearWord(doc, path):
            return clearWords(doc, path)

        def clearWords(doc, *paths):
            words = []
            for path in paths:
                word = doc.get_word(path)
                word.clear()
                words.append(word)
            data_edits.append(DataEdit(cmd="clearWords", paths=paths))
            return words

        def clearChar(doc, path, clearChar):
            word = doc.get_word(path)
            for char in clearChar:
                word.clear(char)
            data_edits.append(DataEdit(cmd="clearChar", paths=[path]))
            return word

        def newWord(doc, text, xpath, ypath):
            xword = doc.get_word(xpath)
            yword = doc.get_word(ypath)
            page = doc.get_page(xpath)

            box = Shape.build_box([xword.xmin, yword.ymin, xword.xmax, yword.ymax])
            word = page.add_word(text, box)
            data_edits.append(DataEdit(cmd="newWord", paths=[xpath, ypath]))
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
            data_edits.append(DataEdit(cmd="newAdjWord", paths=[path]))
            return new_word

        def mergeWords(doc, *paths):
            assert len(paths) > 1
            to_merge_words = [doc.get_word(p) for p in paths[1:]]
            to_merge_text = "".join(w.text for w in to_merge_words)

            main_word = doc.get_word(paths[0])
            new_text = main_word.text + to_merge_text

            main_word.replaceStr("<all>", new_text)
            data_edits.append(DataEdit(cmd="mergeWords", paths=paths))
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
            data_edits.append(DataEdit(cmd="splitWord", paths=[path]))
            return word

        def replaceStr(doc, path, old, new):
            word = doc.get_word(path)
            word.replaceStr(old, new)
            data_edits.append(DataEdit(cmd="replaceStr", paths=[path]))
            return word

        def moveEdge(doc, path, coord, direction, num_thou=5):
            return moveEdges(doc, path, coord, direction, num_thou)

        def moveEdges(doc, path, coord, direction, num_thou=5):
            edge_paths = doc.get_edge_paths(path)
            edges = []
            for path in edge_paths:
                edge = doc.get_edge(path)
                idx = int(coord[1])
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
                edges.append(edge)
            data_edits.append(DataEdit(cmd="moveEdges", paths=edge_paths))
            return edges

        def addWords(doc, region_path, *word_paths):
            region = doc.get_region(region_path)
            add_words = [doc.get_word(p) for p in word_paths]
            region.words += add_words
            # region.text_ = None
            region.shape_ = None
            data_edits.append(DataEdit(cmd="addWords", paths=[region_path, *word_paths]))
            return region

        def addWordIdxs(doc, region_path, *word_idxs):
            region = doc.get_region(region_path)
            # add_words = [doc.get_word(p) for p in word_paths]
            region["word_idxs"] += list(int(idx) for idx in word_idxs)
            # region.text_ = None
            data_edits.append(DataEdit(cmd="addWordIdxs", paths=[region_path]))
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
            for page in doc.pages[del_idx:]:
                page.page_idx -= 1
            data_edits.append(DataEdit(cmd="deletePage", paths=[path]))

        if line_nums:
            assert len(line_nums) == len(edits)

        data_edits = []  # list of lists, constisting of items edited

        for edit, line_num in zip_longest(edits, line_nums, fillvalue=""):
            # print(f"Edit: {edit}")
            editList = shlex.split(edit.strip())
            proc = editList.pop(0)

            cmd = locals().get(proc, None)
            if not cmd:
                file_str = str(file_path)
                line_str = f"{file_str}:{line_num}" if (file_path or line_num) else ""
                raise ValueError(Errors.E020.format(line_num=line_str, function=proc))

            cmd(self, *editList)
        assert len(data_edits) == len(edits)
        self.add_edits(data_edits)
