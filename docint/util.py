import inspect
import os
from pathlib import Path
from typing import Any, Callable, List, Mapping

import yaml
from dateutil import parser

from .errors import Errors


class SimpleFrozenDict(dict):
    """Simplified implementation of a frozen dict, mainly used as default
    function or method argument (for arguments that should default to empty
    dictionary). Will raise an error if user or spaCy attempts to add to dict.
    """

    def __init__(self, *args, error: str = Errors.E002, **kwargs) -> None:
        """Initialize the frozen dict. Can be initialized with pre-defined
        values.

        error (str): The error message when user tries to assign to dict.
        """
        super().__init__(*args, **kwargs)
        self.error = error

    def __setitem__(self, key, value):
        raise NotImplementedError(self.error)

    def pop(self, key, default=None):
        raise NotImplementedError(self.error)

    def update(self, other):
        raise NotImplementedError(self.error)


class SimpleFrozenList(list):
    """Wrapper class around a list that lets us raise custom errors if certain
    attributes/methods are accessed. Mostly used for properties like
    Language.pipeline that return an immutable list (and that we don't want to
    convert to a tuple to not break too much backwards compatibility). If a user
    accidentally calls nlp.pipeline.append(), we can raise a more helpful error.
    """

    def __init__(self, *args, error: str = Errors.E003) -> None:
        """Initialize the frozen list.

        error (str): The error message when user tries to mutate the list.
        """
        self.error = error
        super().__init__(*args)

    def append(self, *args, **kwargs):
        raise NotImplementedError(self.error)

    def clear(self, *args, **kwargs):
        raise NotImplementedError(self.error)

    def extend(self, *args, **kwargs):
        raise NotImplementedError(self.error)

    def insert(self, *args, **kwargs):
        raise NotImplementedError(self.error)

    def pop(self, *args, **kwargs):
        raise NotImplementedError(self.error)

    def remove(self, *args, **kwargs):
        raise NotImplementedError(self.error)

    def reverse(self, *args, **kwargs):
        raise NotImplementedError(self.error)

    def sort(self, *args, **kwargs):
        raise NotImplementedError(self.error)


# def load_config(
#     path: Union[str, Path],
#     overrides: Dict[str, Any] = SimpleFrozenDict(),
#     interpolate: bool = False,
# ) -> Dict[str, Any]:
#     pass


def get_object_name(obj: Any) -> str:
    """Get a human-readable name of a Python object, e.g. a pipeline component.

    obj (Any): The Python object, typically a function or class.
    RETURNS (str): A human-readable name.
    """
    if hasattr(obj, "name") and obj.name is not None:
        return obj.name
    if hasattr(obj, "__name__"):
        return obj.__name__
    if hasattr(obj, "__class__") and hasattr(obj.__class__, "__name__"):
        return obj.__class__.__name__
    return repr(obj)


def get_arg_names(func: Callable) -> List[str]:
    """Get a list of all named arguments of a function (regular,
    keyword-only).

    func (Callable): The function
    RETURNS (List[str]): The argument names.
    """
    argspec = inspect.getfullargspec(func)
    return list(dict.fromkeys([*argspec.args, *argspec.kwonlyargs]))


def is_readable(path):
    return path.is_file() and os.access(path, os.R_OK)


def is_writeable_dir(path):
    path = Path(path)
    return path.is_dir() and os.access(path, os.W_OK)


def is_readable_dir(path):
    path = Path(path)
    return path.is_dir() and os.access(path, os.R_OK)


def read_config_from_disk(path):
    path = Path(path)
    if not path.exists():
        return {}

    config = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.FullLoader)
    config = {} if not config else config
    return config


def load_config(config_dir, doc_name, stub):
    config_file_path = Path(config_dir) / f"{doc_name}.{stub}.yml"
    if is_readable(config_file_path):
        return read_config_from_disk(config_file_path)
    elif not config_file_path.exists():
        return {}
    else:
        raise ValueError(f"Config file is not readable: {config_file_path}")


# def load_file_config(config, doc_name, stub):
#     config_file_path = Path(config_dir) / f"{doc_name}.{stub}.yml"
#     single_config_path = Path(config_dir) / f"{doc_name}.yml"
#
#     if is_readable(config_file_path):
#         return read_config_from_disk(config_file_path)
#     elif is_readable(single_config_path):
#         single_dict = read_config_from_disk(single_config_path)
#         result_dict = {}
#         for k, v in single_dict.items():
#             if k.startswith(stub):
#                 if k == stub:
#                     assert instance(v, dict)
#                     result_dict.update(v)
#                 else:
#                     (stub, field) = k.split(".")
#                     assert "." not in field
#                     result_dict[field] = v
#         return result_dict
#     else:
#         raise ValueError(f"Config file is not readable: {config_file_path}")


def find_date(date_line):
    try:
        date_line = date_line.strip("()")
        dt = parser.parse(date_line, fuzzy=True, dayfirst=True)
        # return str(dt.date()), ''
        return dt.date(), ""
    except ValueError as e:
        return None, str(e)


def raise_error(proc_name, proc, docs, e):
    raise e


def _pipe(
    docs,
    proc,
    name: str,
    default_error_handler,
    kwargs: Mapping[str, Any],
):
    print(f"INSIDE _PIPE {proc}")
    if hasattr(proc, "pipe"):
        print(f"INSIDE _PIPE {proc}")
        yield from proc.pipe(docs, **kwargs)
    else:
        # We added some args for pipe that __call__ doesn't expect.
        kwargs = dict(kwargs)
        error_handler = default_error_handler
        if hasattr(proc, "get_error_handler"):
            error_handler = proc.get_error_handler()
        for arg in ["batch_size"]:
            if arg in kwargs:
                kwargs.pop(arg)
        for doc in docs:
            try:
                doc = proc(doc, **kwargs)  # type: ignore[call-arg]
                yield doc
            except Exception as e:
                error_handler(name, proc, [doc], e)
