from typing import Any, Dict, Optional, Union, Iterator, List, Tuple, Iterable, Callable
from pathlib import Path
import functools

from .util import (
    SimpleFrozenList,
    SimpleFrozenDict,
    _pipe,
    get_object_name,
    raise_error,
    get_arg_names,
)

from .errors import Errors
from .doc import Doc

# from .pipeline import Pipe
from dataclasses import dataclass


@dataclass
class FactoryMeta:
    """Dataclass containing information about a component and its defaults
    provided by the @Language.component or @Language.factory decorator. It's
    created whenever a component is defined and stored on the Language class for
    each component instance and factory instance.
    """

    factory: str
    default_config: Optional[Dict[str, Any]] = None  # noqa: E704
    assigns: Iterable[str] = tuple()
    requires: Iterable[str] = tuple()


class Vision:
    factories = {}
    factories_meta = {}

    def __init__(self):
        self._components = []
        self.default_error_handler = raise_error
        self.images_dir = '.img'
        self.image_root = '.img' # We should be using this 

    @classmethod
    def from_config(cls, config: Dict[str, Any]):
        viz = Vision()
        viz.images_dir = config.get('images_dir', '.img')
        viz.image_root = config.get('image_root', '.img')
        Doc._image_root = viz.image_root
            
        viz.ignore_docs = config.get('ignore_docs', [])
        for pipe_config in config["pipeline"]:
            viz.add_pipe(
                pipe_config.get("name"),
                pipe_config=pipe_config.get("config", {}),
            )
            print(f'Added {pipe_config.get("name")}')
        
        return viz

    def build_doc(self, pdf_path):
        return Doc.build_doc(pdf_path, self.images_dir)

    def add_pipe(
        self,
        factory_name: str,
        *,
        name: Optional[str] = None,
        before: Optional[Union[str, int]] = None,
        after: Optional[Union[str, int]] = None,
        first: Optional[bool] = None,
        last: Optional[bool] = None,
        pipe_config: Dict[str, Any] = {},
    ):
        name = name if name is not None else factory_name
        if name in self.component_names:
            raise ValueError(Errors.E004.format(name=name, opts=self.component_names))

        if factory_name not in self.factories:
            raise ValueError(
                Errors.E005.format(
                    factory_name=factory_name, opts=self.factories.keys()
                )
            )

        factory_meta = self.factories_meta[factory_name]
        default_config = factory_meta.default_config
        new_config = {**default_config, **pipe_config}
        pipe_component = self.factories[factory_name](**new_config)

        pipe_index = self._get_pipe_index(before, after, first, last)
        self._components.insert(pipe_index, (name, pipe_component))
        return pipe_component

    def _get_pipe_index(
        self,
        before: Optional[Union[str, int]] = None,
        after: Optional[Union[str, int]] = None,
        first: Optional[bool] = None,
        last: Optional[bool] = None,
    ) -> int:
        """Determine where to insert a pipeline component based on the before/
        after/first/last values.

        before (str): Name or index of the component to insert directly before.
        after (str): Name or index of component to insert directly after.
        first (bool): If True, insert component first in the pipeline.
        last (bool): If True, insert component last in the pipeline.
        RETURNS (int): The index of the new pipeline component.
        """
        all_args = {"before": before, "after": after, "first": first, "last": last}
        if sum(arg is not None for arg in [before, after, first, last]) >= 2:
            raise ValueError(
                Errors.E006.format(args=all_args, opts=self.component_names)
            )
        if last or not any(value is not None for value in [first, before, after]):
            return len(self._components)
        elif first:
            return 0
        elif isinstance(before, str):
            if before not in self.component_names:
                raise ValueError(
                    Errors.E007.format(name=before, opts=self.component_names)
                )
            return self.component_names.index(before)
        elif isinstance(after, str):
            if after not in self.component_names:
                raise ValueError(
                    Errors.E008.format(name=after, opts=self.component_names)
                )
            return self.component_names.index(after) + 1
        # We're only accepting indices referring to components that exist
        # (can't just do isinstance here because bools are instance of int, too)
        elif type(before) == int:
            if before >= len(self._components) or before < 0:
                err = Errors.E008.format(
                    dir="before", idx=before, opts=self.component_names
                )
                raise ValueError(err)
            return before
        elif type(after) == int:
            if after >= len(self._components) or after < 0:
                err = Errors.E009.format(
                    dir="after", idx=after, opts=self.component_names
                )
                raise ValueError(err)
            return after + 1
        raise ValueError(Errors.E006.format(args=all_args, opts=self.component_names))

    def __call__(
        self,
        path: Path,
        component_cfg: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Doc:
        path = Path(path)
        if path.suffix.lower() in ('.json', '.msgpack', '.jsn'):
            doc = Doc.from_disk(path)
        else:
            doc = self.build_doc(path)

            
        if component_cfg is None:
            component_cfg = {}

        print("Inside __call__")

        for name, proc in self.pipeline:
            if not hasattr(proc, "__call__"):
                raise ValueError(Errors.E003.format(component=type(proc), name=name))
            error_handler = self.default_error_handler
            if hasattr(proc, "get_error_handler"):
                error_handler = proc.get_error_handler()
            try:
                # doc = proc(doc, **component_cfg.get(name, {}))  # type: ignore[call-arg]
                doc = proc(doc)  # type: ignore[call-arg]
            except KeyError as e:
                # This typically happens if a component is not initialized
                raise ValueError(Errors.E109.format(name=name)) from e
            except Exception as e:
                raise
                #error_handler(name, proc, [doc], e)
            if doc is None:
                raise ValueError("Errors.E005.format(name=name)")
        return doc

    def pipe_all(self, paths):
        print("INSIDE PIPE")
        paths = (Path(p) for p in paths)        
        pipes = []
        for name, proc in self.pipeline:
            kwargs = {}
            f = functools.partial(
                _pipe,
                proc=proc,
                name=name,
                kwargs=kwargs,
                default_error_handler=self.default_error_handler,
            )
            pipes.append(f)


        print(f'Building docs...')            
        docs = list(self.build_doc(p) if p.suffix == '.pdf' else Doc.from_disk(p) for p in paths)
        print(f'Before {len(docs)}')
        
        # filter based on ignore_files
        docs = [ d for d in docs if d.pdf_name not in self.ignore_docs]
        print(f'After {len(docs)}')        
        
        for pipe in pipes:
            docs = pipe(docs)
        print("Leaving PIPE")            
        return docs

    @property
    def factory_names(self) -> List[str]:
        """Get names of all available factories.

        RETURNS (List[str]): The factory names.
        """
        names = list(self.factories.keys())
        return SimpleFrozenList(names)

    @property
    def components(self) -> List[Tuple[str, "Pipe"]]:
        """Get all (name, component) tuples in the pipeline, including the
        currently disabled components.
        """
        return SimpleFrozenList(
            self._components, error=Errors.E926.format(attr="components")
        )

    @property
    def component_names(self) -> List[str]:
        """Get the names of the available pipeline components. Includes all
        active and inactive pipeline components.

        RETURNS (List[str]): List of component name strings, in order.
        """
        names = [pipe_name for pipe_name, _ in self._components]
        return SimpleFrozenList(
            names, error='Errors.E926.format(attr="component_names")'
        )

    @property
    def pipeline(self) -> List[Tuple[str, "Pipe"]]:
        """The processing pipeline consisting of (name, component) tuples. The
        components are called on the Doc in order as it passes through the
        pipeline.

        RETURNS (List[Tuple[str, Pipe]]): The pipeline.
        """
        pipes = [(n, p) for n, p in self._components]
        return SimpleFrozenList(pipes, error='Errors.E926.format(attr="pipeline")')

    @property
    def pipe_names(self) -> List[str]:
        """Get names of available active pipeline components.

        RETURNS (List[str]): List of component name strings, in order.
        """
        names = [pipe_name for pipe_name, _ in self.pipeline]
        return SimpleFrozenList(names, error='Errors.E926.format(attr="pipe_names")')

    @property
    def pipe_factories(self) -> Dict[str, str]:
        """Get the component factories for the available pipeline components.

        RETURNS (Dict[str, str]): Factory names, keyed by component names.
        """
        factories = {}
        for pipe_name, pipe in self._components:
            factories[pipe_name] = self.get_pipe_meta(pipe_name).factory
        return SimpleFrozenDict(factories)

    @classmethod
    def factory(
        cls,
        name: str,
        *,
        default_config: Dict[str, Any] = SimpleFrozenDict(),
        assigns: Iterable[str] = SimpleFrozenList(),
        requires: Iterable[str] = SimpleFrozenList(),
        func: Optional[Callable] = None,
    ) -> Callable:
        if not isinstance(name, str):
            raise ValueError('Errors.E963.format(decorator="factory")')

        if not isinstance(default_config, dict):
            err = "Error"
            raise ValueError(err)

        def add_factory(factory_func: Callable) -> Callable:
            factory_meta = FactoryMeta(
                factory=name,
                default_config=default_config,
                assigns=assigns,
                requires=requires,
            )

            cls.factories_meta[name] = factory_meta
            cls.factories[name] = factory_func
            arg_names = get_arg_names(factory_func)
            return factory_func

        if func is not None:  # Support non-decorator use cases
            return add_factory(func)
        return add_factory

    @classmethod
    def component(
        cls,
        name: str,
        *,
        assigns: Iterable[str] = SimpleFrozenList(),
        requires: Iterable[str] = SimpleFrozenList(),
        func: Optional["Pipe"] = None,
    ) -> Callable:

        if name is not None and not isinstance(name, str):
            raise ValueError('Errors.E963.format(decorator="component")')

        component_name = name if name is not None else get_object_name(func)

        def add_component(component_func) -> Callable:
            if isinstance(func, type):  # function is a class
                raise ValueError("Errors.E965.format(name=component_name)")

            def factory_func() -> "Pipe":
                return component_func

            cls.factory(
                component_name,
                assigns=assigns,
                requires=requires,
                func=factory_func,
            )
            return component_func

        if func is not None:  # Support non-decorator use cases
            return add_component(func)
        return add_component

    def get_pipe(self, name: str) -> "Pipe":
        """Get a pipeline component for a given component name.

        name (str): Name of pipeline component to get.
        RETURNS (callable): The pipeline component.

        DOCS: https://spacy.io/api/language#get_pipe
        """
        for pipe_name, component in self._components:
            if pipe_name == name:
                return component
        raise KeyError("Errors.E001.format(name=name, opts=self.component_names)")

    def has_pipe(self, name: str) -> bool:
        """Check if a component name is present in the pipeline. Equivalent to
        `name in nlp.pipe_names`.

        name (str): Name of the component.
        RETURNS (bool): Whether a component of the name exists in the pipeline.

        DOCS: https://spacy.io/api/language#has_pipe
        """
        return name in self.pipe_names
