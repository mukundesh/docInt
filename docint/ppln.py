import logging
import os
from collections import ChainMap
from dataclasses import dataclass
from itertools import chain, groupby
from operator import itemgetter
from pathlib import Path
from types import GeneratorType
from typing import Callable, Dict, Iterable, List, Optional, Union

from pydantic import BaseModel, BaseSettings, DirectoryPath, Field, create_model, validate_model
from pydantic.fields import FieldInfo

from .audio import Audio
from .doc import Doc
from .file import File
from .util import load_config, read_config_from_disk
from .video import Video

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
##

## Scope order
# 1. Code Defaults
# 2. Pipeline File
# 3. Environment Variables
# 4. Commandline Variables

# Scoped Configs
# 1. Pipeline File
# 2. Scope_config_file
# 3. Environment Variables
# 4. Commandline Variables

"""
## Decisions Taken
1. Pipeline config and component config will be different, pipeline_config needs to be defined
   in code of ppln.py, I am sceptical of allowing global config by just adding them to the ppln.py
   file.

2. You can add scoped_config to pipeline.yml, by adding a section called 'scoped_config:'
   but then you need to define them just like environment variables, 'seperted by '__'
"""


class PipeConfig:
    # Container config class, each dict in chain_map is validated against component_setting_cls
    def __init__(self, pipe_name, component_setting_cls):
        self.component_setting_cls = component_setting_cls
        self.pipe_name = pipe_name

        settings = self.component_setting_cls(stub=pipe_name.lower())
        self.validate(settings.dict())

        self.chain_map = ChainMap(settings.dict())
        self.scopes = []

        print(self.chain_map)
        self.config_keys = list(k.lower() for k in self.chain_map.keys())

        self.scopes_dict = self.load_env(pipe_name)

    def __getattr__(self, name):
        return self.chain_map[name]

    def validate(self, config_dict):
        dict_str, set_str, validation_error = validate_model(
            self.component_setting_cls, config_dict
        )
        if validation_error:
            print(config_dict)
            raise validation_error

    def load_env(self, pipe_name):
        env_prefix = self.component_setting_cls.__config__.env_prefix
        env_nested_delimiter = self.component_setting_cls.__config__.env_nested_delimiter

        prefix = f"{env_prefix}{pipe_name.upper()}{env_nested_delimiter}"
        keys_list = []
        for env_name, env_val in os.environ.items():
            # print("\t", env_name)
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

    def add_scope_config(self, scope_str, config_dict):
        if config_dict:
            config_dict.setdefault("stub", self.pipe_name.lower())
            self.validate(config_dict)
            self.scopes_dict.setdefault(scope_str, []).append(config_dict)

    def enter_scope(self, scope):
        def merge_dicts(dict_list):
            return {k: v for d in reversed(dict_list) for k, v in d.items()}

        if "=" in scope:
            raise ValueError("Scope definition cannot have '.'")

        self.scopes.append(scope)
        scope_str = "=".join(self.scopes)
        self.chain_map = self.chain_map.new_child(merge_dicts(self.scopes_dict.get(scope_str, [])))

    def exit_scope(self):
        self.scopes.pop(-1)
        self.chain_map = self.chain_map.parents


class PipelineSettings(BaseSettings):
    root_dir: Optional[DirectoryPath] = Field(
        default=".", description="Root directory of processing"
    )
    input_dir: Optional[DirectoryPath] = Field(
        default=".", description="input directory for processing"
    )
    output_dir: Optional[DirectoryPath] = Field(
        default=".", description="output directory for processing"
    )
    config_dir: Optional[DirectoryPath] = Field(
        default=".", description="configuration directory for processing"
    )
    ignore_docs: Union[List[str], Dict[str, str]] = Field(
        default=[], description="files to ignore."
    )
    read_cache: bool = Field(default=True, description="Whether to read cached data")

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

    def __init__(self, pipeline_config={}):
        self._pipes = []
        self._config = PipelineSettings(**pipeline_config)
        self._pipe_configs = []
        self._single_file = False  # pipeline invoked with 1 file, TODO should this be called debug?

    @classmethod
    def from_file(cls, pipeline_file):
        ppln_dict = read_config_from_disk(pipeline_file)
        return cls.from_config(ppln_dict)

    @classmethod
    def from_config(cls, pipeline_file_dict):
        ppln_dict = pipeline_file_dict.pop("pipeline", [])
        scope_configs = pipeline_file_dict.pop("scope_configs", {})  # noqa

        # ppln_config = pipeline_file_dict # TODO use this to initialize pipeline_config
        ppln = Pipeline(pipeline_file_dict)
        for pipe_dict in ppln_dict:
            if isinstance(pipe_dict, dict):
                pipe_name = pipe_dict.pop("name")
                component_name = pipe_dict.pop("component_name", pipe_name)
                ppln.add_pipe(
                    pipe_name, component_name, pipe_dict.get("config", {}), pipeline_file_dict
                )
            else:
                pipe_name = pipe_dict
                ppln.add_pipe(pipe_name, pipe_name, {}, pipeline_file_dict)
        return ppln

    def create_component_settings(self, component_name):
        def get_config_info(config_cls_list):
            annot_list = [c.__dict__.get("__annotations__", {}) for c in config_cls_list]
            vars_list = [vars(c) for c in config_cls_list]

            annot_dict = {k: v for d in annot_list for k, v in d.items()}
            vars_dict = {k: v for d in vars_list for k, v in d.items()}
            return annot_dict, vars_dict

        component_cls = Pipeline.components[component_name]

        # Read all the fields defined in the Config class
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

    def add_pipe(self, pipe_name, component_name, component_configs, pipeline_configs):
        if component_name not in Pipeline.components:
            raise ValueError(f"Unknown component name {component_name}")

        if pipe_name in [n for (n, c) in self._pipes]:
            raise ValueError(f"Pipe {pipe_name} exists in the pipeline.")

        # create a settings class that is a subclass of pipline_settings
        component_cls = Pipeline.components[component_name]
        component_settings_cls = self.create_component_settings(component_name)

        # create a config
        pipe_config = PipeConfig(pipe_name, component_settings_cls)
        for attr, value in chain(pipeline_configs.items(), component_configs.items()):
            setattr(pipe_config, attr, value)
        self._pipe_configs.append(pipe_config)

        pipe = component_cls(cfg=pipe_config, pipe_name=pipe_name)
        print(pipe)
        self._pipes.append((pipe_name, pipe))

    @classmethod
    def check_component_definition(cls, component_cls):
        # print("\t check_component_definition")
        pass

    @classmethod
    def register_component(
        cls,
        *,
        requires: Iterable[str] = [],
        assigns: Iterable[str] = [],
        depends: Iterable[str] = [],
    ) -> Callable:
        # print("Inside register_component: " + assigns)

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
            # print("Inside register_component_cls: " + str(component_cls))
            return component_cls

        return register_component_cls

    def is_ignored(self, file_path):
        # print(self._config.ignore_docs)
        return any(i in file_path.name for i in self._config.ignore_docs)

    def file_needs_processing(self, file_path):
        # TODO: Needs processing fields
        # 3 fields needed are not defined return True for all
        if not self.has_processing_fields:
            return True

        # if output_file does not exist, return True
        file_name = file_path.name
        output_path = self.pipe_cfg.output_dir / f"{file_name}.{self.pipe_cfg.output_stub}.json"
        if not output_path.exists():
            return True

        output_ts = output_path.stat().st_mtime

        # if output_time < input_time do the processing
        if file_path.exists():
            input_ts = file_path.stat().st_mtime
            if input_ts > output_ts:
                return True

        # if pipe_config_time > output_time do the processing, config changed
        for (pipe_name, pipe), pipe_cfg in zip(self._pipes, self._pipe_configs):
            pipe_cfg_path = self.pipe_cfg.config_dir / f"{file_name}.{pipe_cfg.stub}.yml"
            if pipe_cfg_path.exists() and pipe_cfg_path.stat().st_mtime > output_ts:
                return True

        return False

    def build_file(self, file_path):
        if isinstance(file_path, File):  # Doc
            return file_path

        file_path = Path(file_path)
        if file_path.suffix.lower() in (".json"):
            file = Doc.from_disk(file_path)
        elif file_path.suffix.lower() == ".pdf":
            file = Doc.build_doc(file_path)
        elif file_path.suffix.lower() in (".webm", ".mp3"):
            file = Audio.build(file_path)
        elif file_path.suffix.lower() in (".mp4"):
            file = Video.build(file_path)
        else:
            raise ValueError(f"Unknown document format {file_path}")
        return file

    def exec_pipe(self, pipe_name, pipe, pipe_cfg, files):
        def setup_pipe(file):
            file.add_pipe(pipe_name)  # please change the name of method

            # read config directory
            file_cfg_dict = load_config(pipe_cfg.config_dir, file.file_name, pipe_cfg.stub)
            scope_configs = file_cfg_dict.pop("scope_configs", {})
            pipe_cfg.add_scope_config(file.file_name, file_cfg_dict)
            for file_scope_str, scope_config in scope_configs.items():
                scope_str = f"{file.file_name}={file_scope_str}"
                pipe_cfg.add_scope_config(scope_str, file_cfg_dict)

            # configure loggers
            pipe_cfg.enter_scope(file.file_name)

        def tear_down(file):
            pipe_cfg.exit_scope()
            assert len(pipe_cfg.scopes) == 0

        for file in files:
            setup_pipe(file)
            try:
                file = pipe(file, pipe_cfg)
            except Exception as e:
                print(f"*** Failed *** {e}")
                if self._single_file:
                    raise
                else:
                    continue
            finally:
                tear_down(file)
            if file is None:
                raise ValueError("Document not returned")
            yield file

    def __call__(self, file_paths):
        if isinstance(file_paths, (list, GeneratorType)):
            # files = (self.build_file(f) for f in file_paths if not self.is_ignored(f) and self.file_needs_processing(f))
            files = (self.build_file(f) for f in file_paths if not self.is_ignored(f))
            self._single_file = False
        else:
            # A single file is never ignored !
            self._single_file = True
            files = [self.build_file(file_paths)]

        for (pipe_name, pipe), pipe_cfg in zip(self._pipes, self._pipe_configs):
            try:
                files = self.exec_pipe(pipe_name, pipe, pipe_cfg, files)
            except KeyError as e:  # noqa
                # This typically happens if a component is not initialized
                raise ValueError("Key errorr, looks like config changed")
            except Exception as e:
                raise e
                # error_handler(name, proc, [doc], e)

        if isinstance(file_paths, (list, GeneratorType)):
            return files
        else:
            files = list(files)
            return files[0] if len(files) == 1 else None


class Component(BaseModel):
    lgr: logging.Logger = None
    cfg: PipeConfig  # Needs to go, as cfg should be passed
    pipe_name: str

    class Config:
        arbitrary_types_allowed = True
        stub: str


"""
@Pipeline.register_component(
    assigns="words",
    depends=["pip:google-cloud-vision"],
    requires="pages",
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

            self.cfg.exit_scope(f"page[{page.page_idx}]")
"""


# os.environ['RECOGNIZER__PAGE_ANGLE'] = 4.0
# os.environ['RECOGNIZER__RAJPOL-32__PAGE_ANGLE'] = 3.0
# os.environ['RECOGNIZER__RAJPOL-32__PAGEIDX-0__PAGE_ANGLE'] = 2.0

# pipeline = Pipeline.from_config({"pipeline": ["Recognizer"]})
