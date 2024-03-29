import platform

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
        print(f"*** Running do_nothing {platform.system()}-{platform.release()}")
        return doc
