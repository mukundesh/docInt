from pathlib import Path
from typing import Any, Dict

from . import pipeline
from .errors import Errors
from .util import SimpleFrozenDict, is_readable, read_config_from_disk
from .vision import Vision


def load(name: Path, *, config: Dict[str, Any] = SimpleFrozenDict()) -> Vision:
    """Load a docInt model from either local path.

    Args:
        name (Path): Path to the model config file
        config (Dict[str, Any]): Config options
    Returns:
        Vision: A loaded viz object.

        .. _PEP 484:
            https://www.python.org/dev/peps/pep-0484/

    """
    path = Path(name)

    if not is_readable(path):
        raise IOError(Errors.E001.format(path=path))

    config = read_config_from_disk(path)
    return Vision.from_config(config)


def empty(*, config: Dict[str, Any] = SimpleFrozenDict()) -> Vision:
    """Create an empty docInt model

    Args:
        config (Dict[str, Any]): Config options
    Returns:
        Vision: A loaded viz object.
    """
    return Vision.from_config(config)
