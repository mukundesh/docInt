import logging
import os
from collections import ChainMap
from dataclasses import dataclass
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Union

from pydantic import BaseModel, BaseSettings, DirectoryPath, Field, create_model, validate_model
from pydantic.fields import FieldInfo

## This file is still WIP
# TODO
# 1. Implement add_scope and pop_scope
# 2. Merge methods for update
# 3. Implement load_config file that has scopes
# 4. Print scope strings
# 5. Testing
# 6. Read Pipeline_Config

# Notes
# 1. Understand the different between Config (User facing) and Setting (internal object for validation)
# 2. Concept of scope
# 3. Currently leaning towards passing the config object to the __call__ method, instead of it being a member variable
# 4. Notion of component and pipeline config


class PipeConfig:
    # Container config class, each dict in chain_map is validated against component_setting_cls
    def __init__(self, pipe_name, component_setting_cls):
        self.component_setting_cls = component_setting_cls
        self.pipe_name = pipe_name

        self.chain_map = ChainMap()
        settings = self.component_setting_cls(stub=pipe_name)
        self.validate(settings.dict())

        self.chain_map = self.chain_map.new_child(settings.dict())
        self.scopes = []

        print(self.chain_map)
        self.config_keys = list(k.lower() for k in self.chain_map.keys())

        self.scopes_dict = self.load_env(pipe_name)

    def validate(self, config_dict):
        dict_str, set_str, validation_error = validate_model(
            self.component_setting_cls, config_dict
        )
        if validation_error:
            raise validation_error

    def load_env(self, pipe_name):
        env_prefix = self.component_setting_cls.__config__.env_prefix
        env_nested_delimiter = self.component_setting_cls.__config__.env_nested_delimiter

        prefix = f"{env_prefix}{pipe_name.upper()}{env_nested_delimiter}"
        keys_list = []
        for env_name, env_val in os.environ.items():
            print("\t", env_name)
            if not env_name.startswith(prefix):
                continue
            # remove the prefix before splitting in case prefix has
            # characters in common with the delimiter
            env_name_without_prefix = env_name[len(prefix) :]
            keys = env_name_without_prefix.split(env_nested_delimiter)

            # keys contains some scope strings and some config strings. Anything that
            # is not a config field is a scope string, and the first config string separtes
            # the two strings.
            config_idx = max(
                (idx for (idx, k) in enumerate(keys) if k.lower() in self.config_keys), default=0
            )

            scope_str = env_nested_delimiter.join(keys[:config_idx])

            keys_list.append((scope_str, keys[config_idx:], env_val))
        # end for

        # group all scope_keys
        scopes_dict = {}
        keys_list.sort(key=itemgetter(0))
        for scope_str, keys_group in groupby(keys_list, key=itemgetter(0)):
            scope_key = tuple(scope_str.split(env_nested_delimiter))
            scope_dict = scopes_dict.setdefault(scope_key, {})
            for _, config_keys, env_val in keys_group:
                env_var = scope_dict
                for key in config_keys[:-1]:
                    env_var = env_var.setdefault(key, {})
                env_var[config_keys[-1]] = env_val

        print(scopes_dict)
        return scopes_dict

    def add_scope_config(self, scope_key, config):
        self.scopes_dict.setdefault(scope_key, {}).update(config)

    def add_scope(self, scope):
        self.scopes.append(scope)
        self.update()

    def pop_scope(self, scope):
        self.scopes.pop(-1)
        self.update()

    def load_dotfile(self):
        pass

    def load_configfile(self):
        pass


class PipelineSettings(BaseSettings):
    repo_dir: Optional[DirectoryPath] = Field(description="Root directory of processing")
    ignore_docs: Union[List[str], Dict[str, str]] = []

    class Config:
        extra = "allow"
        env_prefix = "DI_"
        env_nested_delimiter = "__"


@dataclass
class ComponentMeta:
    name: str
    assigns: Iterable[str] = tuple()
    requires: Iterable[str] = tuple()
    depends: Iterable[str] = tuple()


class Pipeline:
    components = {}
    components_meta = {}

    class Config:
        ignore_docs = []
        description = ""

    def __init__(self):
        self._pipes = []

    @classmethod
    def from_file(cls, pipeline_file):
        ppln_dict = {}  # read_config_from_disk(pipeline_file)
        return cls.from_config(ppln_dict)

    @classmethod
    def from_config(cls, pipeline_file_dict):
        ppln_dict = pipeline_file_dict.pop("pipeline", [])
        # ppln_config = pipeline_file_dict # TODO use this to initialize pipeline_config

        ppln = Pipeline()
        for pipe_dict in ppln_dict:
            if isinstance(pipe_dict, dict):
                pipe_name = pipe_dict.pop("name")
                component_name = pipe_dict.pop("component_name", pipe_name)
                ppln.add_pipe(pipe_name, component_name, pipe_dict.get("config", {}))
            else:
                pipe_name = pipe_dict
                ppln.add_pipe(pipe_name, pipe_name, {})
        return ppln

    def create_component_settings(self, component_name):
        def get_config_info(config_cls_list):
            annot_list = [c.__dict__.get("__annotations__", {}) for c in config_cls_list]
            vars_list = [vars(c) for c in config_cls_list]

            annot_dict = {k: v for d in annot_list for k, v in d.items()}
            vars_dict = {k: v for d in vars_list for k, v in d.items()}
            return annot_dict, vars_dict

        component_cls = Pipeline.components[component_name]
        config_cls_list = [getattr(c, "Config", {}) for c in component_cls.__mro__]
        config_cls_list = [cfg_cls for cfg_cls in config_cls_list if cfg_cls]

        all_annotations, all_vars = get_config_info(config_cls_list)

        field_definitions = {}
        for field_name, field_type in all_annotations.items():
            if isinstance(field_type, FieldInfo):
                field_definitions[field_name] = field_type
            elif field_name in all_vars:
                field_val = all_vars[field_name]
                field_definitions[field_name] = (field_type, field_val)
            else:
                field_definitions[field_name] = (field_type, ...)

        config_model = create_model(
            f"{component_name}Settings", __base__=PipelineSettings, **field_definitions
        )
        print(config_model.__fields__)
        return config_model

    def add_pipe(self, pipe_name, component_name, pipe_config):
        if component_name not in Pipeline.components:
            raise ValueError(f"Unknown component name {component_name}")

        if pipe_name in [n for (n, c) in self._pipes]:
            raise ValueError(f"Pipe {pipe_name} exists in the pipeline.")

        component_cls = Pipeline.components[component_name]
        component_settings_cls = self.create_component_settings(component_name)

        pipe_config = PipeConfig(pipe_name, component_settings_cls)

        pipe = component_cls(cfg=pipe_config, pipe_name=pipe_name)
        print(pipe)
        self._pipes.append((pipe_name, pipe))

    @classmethod
    def check_component_definition(cls, component_cls):
        print("\t check_component_definition")
        pass

    @classmethod
    def register_component(
        cls,
        *,
        requires: Iterable[str] = [],
        assigns: Iterable[str] = [],
        depends: Iterable[str] = [],
    ) -> Callable:
        print("Inside register_component: " + assigns)

        def register_component_cls(component_cls):
            cls.check_component_definition(component_cls)

            name = component_cls.__name__
            cls.components[name] = component_cls
            cls.components_meta[name] = ComponentMeta(
                name=name,
                requires=requires,
                assigns=assigns,
                depends=depends,
            )
            print("Inside register_component_cls: " + str(component_cls))
            return component_cls

        return register_component_cls

    def __call__(self, path_doc, pipe_configs):
        if isinstance(path_doc, int):  # Doc
            doc = path_doc
        elif isinstance(path_doc, str) or isinstance(path_doc, Path):
            path = path_doc
            if path.suffix.lower() in (".json", ".jsn", ".msgpack"):
                doc = None  # Doc.from_disk(path)
            elif path.suffix.lower() == ".pdf":
                doc = None  # Doc.build_doc(path)
        else:
            raise ValueError(f"Unknown document format {path_doc}")

        for name, pipe in self._pipes:
            if name in pipe_configs:
                pipe.cfg.load_dict(pipe_configs[name])

            try:
                doc = self.exec_pipe(name, pipe, doc)
            except KeyError as e:  # noqa
                # This typically happens if a component is not initialized
                raise ValueError("Key errorr, looks like config changed")
            except Exception as e:
                raise e
                # error_handler(name, proc, [doc], e)

            if doc is None:
                raise ValueError("Empty document returned")
        return doc


class Component(BaseModel):
    lgr: logging.Logger = None
    cfg: PipeConfig
    pipe_name: str

    class Config:
        arbitrary_types_allowed = True

        stub: str
        conf_dif: Optional[Path] = Path("conf")
        log_config: Dict[str, str] = {}


@Pipeline.register_component(
    assigns="words",
    depends=["pip:google-cloud-vision"],
    needs="pages",
)
class Recognizer(Component):
    class Config:
        orient_pages: bool = False
        page_angle: float = 0.0
        new_angle: float = Field(description="Root directory of processing", default=0.0)

    def __call__(self, doc):
        self.cfg.load_file(doc.pdf_name)

        for page in doc.pages:
            self.cfg.set_scope(f"page[{page.page_idx}]")

            # do stuff

            self.cfg.pop_scope(f"page[{page.page_idx}]")


# os.environ['RECOGNIZER__PAGE_ANGLE'] = 4.0
# os.environ['RECOGNIZER__RAJPOL-32__PAGE_ANGLE'] = 3.0
# os.environ['RECOGNIZER__RAJPOL-32__PAGEIDX-0__PAGE_ANGLE'] = 2.0

pipeline = Pipeline.from_config({"pipeline": ["Recognizer"]})
