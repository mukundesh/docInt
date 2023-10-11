from typing import List, Tuple

from ..ppln import Component, Pipeline


@Pipeline.register_component(
    assigns="rm_intervals",
    depends=[],
    requires=["meta"],
)
class RemoveIntervals(Component):
    class Config:
        rm_intervals: List[Tuple[int, int]] = []
        extra = "allow"

    def __call__(self, audio, cfg):
        audio.rm_intervals = cfg.rm_intervals
        return audio
