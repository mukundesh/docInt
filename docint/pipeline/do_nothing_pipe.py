import platform

from ..vision import Vision


@Vision.factory(
    "do_nothing_pipe",
    default_config={
        "nothing": 1,
    },
)
class DoNothingPipe:
    def __init__(self, nothing):
        self.nothing = nothing

    def pipe(self, docs):
        print(f"*** Running do_nothing_pipe {platform.system()}-{platform.release()}")
        return docs
