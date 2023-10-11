import shutil
from enum import IntEnum
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List

from more_itertools import flatten
from pydantic import BaseModel

from .data_edit import DataEdit
from .data_error import DataError


class ExtractType(IntEnum):
    BaseType = 0
    Object = 1
    List = 2
    Dict = 3
    DictList = 4


class ExtractInfo(BaseModel):
    field_name: str
    field_type: ExtractType
    module_name: str = None
    class_name: str = None
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


class File(BaseModel):
    _file_path: Path
    extract_infos: Dict[str, ExtractInfo] = {}

    pipe_names: List[str] = []
    errors: Dict[str, List[DataError]] = {}
    edits: Dict[str, List[DataEdit]] = {}

    class Config:
        extra = "allow"

    @property
    def file_path(self):
        return self._file_path

    def get_file_path(self):
        return self._file_path

    @property
    def file_name(self):
        return self._file_path.name

    def get_file_name(self):
        return self._file_path.name

    @property
    def file_stem(self):
        return self._file_path.stem

    @property
    def file_suffix(self):
        return self._file_path.suffix

    def get_file_stem(self):
        return self._file_path.stem

    def get_errors(self, pipe_name):
        return self.errors.get(pipe_name, [])

    def get_edits(self, pipe_name):
        return self.edits.get(pipe_name, [])

    def to_json(self, exclude_defaults=True):
        pass

    def to_dict(self, exclude_defaults=True):
        pass

    def to_disk(self, disk_file, format="json", exclude_defaults=True):
        pass

    def copy_file(self, dst_path):
        shutil.copy(self._file_path, Path(dst_path))

    def add_extract_field(self, field_name, field_type, module_name=None, class_name=None):
        if field_type in (int, float, complex, str):
            field_type = ExtractType.BaseType
        else:
            field_type = {
                "noparse": ExtractType.BaseType,
                "obj": ExtractType.Object,
                "list": ExtractType.List,
                "dict": ExtractType.Dict,
                "dict_list": ExtractType.DictList,
            }[field_type]

        extract_info = ExtractInfo(
            field_name=field_name,
            field_type=field_type,
            module_name=module_name,
            class_name=class_name,
            pipe_name=self.pipe_names[-1],
        )
        self.extract_infos[field_name] = extract_info

    def remove_extract_field(self, field_name):
        del self.extract_infos

    @classmethod
    def from_file(cls, file_path):
        return File(file_path=Path(file_path))

    @classmethod
    def from_dict(cls, file_dict):
        pass

    @classmethod
    def from_disk(cls, json_file):
        pass

    def add_pipe(self, pipe_name):
        self.pipe_names.append(pipe_name)

    def add_errors(self, errors):
        pipe_name = self.pipe_names[-1]
        self.errors.setdefault(pipe_name, []).extend(errors)

    def add_edits(self, edits):
        pipe_name = self.pipe_names[-1]
        self.edits.setdefault(pipe_name, []).extend(edits)
