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
        print(f"*** Running do_nothing_pipe {platform.system()}-{platform.release()}, {type(docs)}")

        for doc in docs:
            yield doc

        # print(f"docs: {type(docs)}")
        # return docs
