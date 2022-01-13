from typing import Any, Dict
from pathlib import Path

from .errors import Errors
from .vision import Vision
from .util import SimpleFrozenDict
from .util import is_readable, read_config_from_disk

from . import pipeline
from .vision import Vision





def load(name: Path, *, config: Dict[str, Any] = SimpleFrozenDict()) -> Vision:
    """Load a docInt model from either local path.

    name (Path): Path to the model config file
    config (Dict[str, Any]): Config options
    RETURNS (Vision): A loaded viz object.
    """
    path = Path(name)

    if not is_readable(path):
        raise IOError(Errors.E001.format(path=path))

    config = read_config_from_disk(path)
    return Vision.from_config(config)


def empty(*, config: Dict[str, Any] = SimpleFrozenDict()) -> None:
    """Create an empty docInt model ** NOT IMPLEMENTED **

    config (Dict[str, Any]): Config options
    RETURNS (Vision): A loaded viz object.
    """
    raise NotImplementedError("Will do when needed")
