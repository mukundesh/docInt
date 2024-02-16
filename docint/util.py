import inspect
import os
import random
import statistics
import string
import time
from pathlib import Path
from subprocess import run
from typing import Any, Callable, List, Mapping

import yaml

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


def get_doc_name(input_path):
    file_name = Path(input_path).name
    pdf_pos = file_name.lower().index(".pdf")
    return file_name[: pdf_pos + 4]


def is_readable(path):
    return path.is_file() and os.access(path, os.R_OK)


def is_writeable_dir(path):
    path = Path(path)
    return path.is_dir() and os.access(path, os.W_OK)


def is_readable_dir(path):
    path = Path(path)
    return path.is_dir() and os.access(path, os.R_OK)


def is_readable_nonempty(path):
    return is_readable(path) and path.stat().st_size > 0


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
    from dateutil import parser

    try:
        date_line = date_line.strip("()")
        dt = parser.parse(date_line, fuzzy=True, dayfirst=True)
        # return str(dt.date()), ''
        return dt.date(), ""
    except ValueError as e:
        return None, str(e)


def raise_error(proc_name, proc, docs, e):
    print(f"**** PIPEERROR IN {docs[0].pdf_name} --> {e}")
    # raise e


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


def generate_docker_src(pipeline_path, input_doc, output_doc):
    s = "import docint\n"
    s += 'if __name__ == "__main__":\n'
    s += f'    viz = docint.load("{str(pipeline_path)}")\n'
    s += f'    doc = viz("{input_doc}")\n'
    s += f'    doc.to_disk("{output_doc}")\n'
    return s


def generate_docker_src_pipe_all(pipeline_path, input_doc_paths, output_doc_paths):
    assert len(input_doc_paths) == len(output_doc_paths)
    all_input_paths_str = ", ".join(f"'{str(p)}'" for p in input_doc_paths)
    all_output_paths_str = ", ".join(f"'{str(p)}'" for p in output_doc_paths)
    s = "import docint\n"
    s += 'if __name__ == "__main__":\n'
    s += f'    viz = docint.load("{str(pipeline_path)}")\n'
    s += f"    docs = viz.pipe_all([{all_input_paths_str}])\n"
    s += f"    for doc, output_doc_str in zip(docs, [{all_output_paths_str}]):\n"
    s += "        doc.to_disk(output_doc_str)\n"
    return s


# https://stackoverflow.com/a/2257449/18159079
#
def get_uniq_str(size=6, chars=string.ascii_uppercase + string.digits, randomize=False):
    if randomize:
        return "".join(random.SystemRandom().choice(chars) for _ in range(size))
    else:
        return "".join(random.choice(chars) for _ in range(size))


# https://stackoverflow.com/a/13790289/18159079
#
def tail(file_path, lines=1, _buffer=4098):
    """Tail a file and get X lines from the end"""
    # place holder for the lines found
    lines_found = []

    # block counter will be multiplied by buffer
    # to get the block size from the end
    block_counter = -1

    with file_path.open() as f:
        # loop until we find X lines
        while len(lines_found) <= lines:
            try:
                f.seek(block_counter * _buffer, os.SEEK_END)
            except IOError:  # either file is too small, or too many lines requested
                f.seek(0)
                lines_found = f.readlines()
                break

            lines_found = f.readlines()
            # decrement the block counter to get the
            # next X bytes
            block_counter -= 1

    return lines_found[-lines:]


# Repo Path management
# Repo path starts from the root directory of a repository (where .git is stored)
# All the paths in Orgpedia are either relative or repo paths.
#


def get_repo_dir(input_dir: Path = None):
    input_dir = Path.cwd() if not input_dir else input_dir
    input_dir = input_dir.resolve()

    if input_dir == Path(input_dir.root):
        return None
    git_path = input_dir / ".git"
    if git_path.exists() and git_path.is_dir():
        return input_dir
    else:
        return get_repo_dir(input_dir.parent)


def is_repo_path(input_dir: str):
    return str(input_dir)[0] == "/"


def get_full_path(repo_path: str, repo_dir: Path = None):
    assert is_repo_path(repo_path)
    repo_dir = get_repo_dir() if not repo_dir else repo_dir
    return repo_dir / str(repo_path)[1:]


def get_repo_path(path: Path, repo_dir: Path = None):
    repo_dir = get_repo_dir(path) if not repo_dir else repo_dir
    relative_path = path.relative_to(repo_dir)
    return f"/{str(relative_path)}"


# Model Directory management
# Should this be a class ModelStore, especially given that
# we are managing a models.yml as well.


def get_model_stub(model_name):
    if ":" in model_name:
        model_src, model_repo = model_name.split(":", 1)
        return Path(model_src) / Path(model_repo)
    else:
        return model_name


def get_git_url(model_name):
    model_src, model_repo = model_name.split(":", 1)
    if model_src == "huggingface":
        return f"https://huggingface.co/{model_repo}"
    else:
        raise NotImplementedError(f"Cannot download {model_name}")


def is_model_downloaded(model_name, model_root_dir):
    model_path = get_model_path(model_name, model_root_dir)
    return model_path.is_dir() and any(model_path.iterdir())


def download_model(model_name, model_root_dir, over_write=False):
    is_downloaded = is_model_downloaded(model_name, model_root_dir)
    assert (not over_write) and not is_downloaded

    git_url = get_git_url(model_name)
    model_path = get_model_path(model_name, model_root_dir)

    completed_process = run(
        ["git", "clone", git_url, str(model_path)], capture_output=True, text=True
    )
    if completed_process.returncode != 0:
        err_str = completed_process.stderr
        raise RuntimeError(f"git failed, with {err_str}")


def get_model_path(model_name, model_root_dir):
    model_repo_path = Path(model_root_dir) / get_model_stub(model_name)
    if model_repo_path.exists():
        return model_repo_path

    model_dot_path = Path(".model") / get_model_stub(model_name)
    if model_dot_path.exists():
        return model_dot_path

    raise ValueError(f"Unable to find {model_name} in {model_dot_path} or {model_repo_path}")


def add_model(model_name, model_root_dir):
    model_src, model_repo = model_name.split(":", 1)
    models_dict = read_config_from_disk(Path(model_root_dir) / "models.yml")
    if model_name not in models_dict:
        if model_name.startswith("huggingface"):
            models_dict[model_name] = {"path": get_git_url(model_name)}
        else:
            models_dict[model_name] = {"path": get_git_url(model_name)}


def mklist(lst):
    return lst if isinstance(list, lst) else [lst]


def avg(iter, default):
    try:
        return statistics.mean(iter)
    except statistics.StatisticsError:
        return default


# decorator to record the time taken for the function
def record_timing(func):
    total_time = 0
    num_count = 0

    def wrapper(*args, **kwargs):
        nonlocal total_time, num_count
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        elapsed_time = end_time - start_time
        total_time += elapsed_time
        num_count += 1
        # print(f"{func.__name__} took {elapsed_time:.6f} seconds (Total: {total_time:.6f} seconds)")
        return result

    def get_total_time():
        return total_time

    def get_avg_time():
        return total_time / num_count

    # Attach the get_total_time function to the wrapper so it can be accessed from outside
    wrapper.get_total_time = get_total_time
    wrapper.get_avg_time = get_avg_time

    return wrapper
