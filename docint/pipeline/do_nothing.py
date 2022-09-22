import platform
from pathlib import Path

from ..vision import Vision


@Vision.factory(
    "do_nothing",
    default_config={
        "nothing": 1,
    },
)
class DoNothing:
    def __init__(self, nothing):
        self.nothing = nothing

    def __call__(self, doc):
        print(f'*** Running do_nothing {platform.system()}-{platform.release()}')
        sys_out_path = Path("output") / "system.out"
        sys_out_path.write_text(f'*** Running do_nothing {platform.system()}-{platform.release()}\n')
        return doc
