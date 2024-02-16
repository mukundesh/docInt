import json
from pathlib import Path

from ..ppln import Component, Pipeline


def get_scene_intervals(video, detector, threshold, merge_last_scene, min_scene_len):
    from scenedetect import AdaptiveDetector, ContentDetector, SceneManager, open_video

    video = open_video(str(video.file_path))
    scene_manager = SceneManager()

    if min_scene_len[-1] == "s":
        min_scene_len_frames = float(min_scene_len[:-1]) * video.frame_rate

    if threshold is not None:
        args = {"threshold": threshold, "min_scene_len": min_scene_len_frames}
    else:
        args = {"min_scene_len": min_scene_len_frames}

    if detector == "content":
        scene_manager.add_detector(ContentDetector(**args))
    elif detector == "adaptive":
        scene_manager.add_detector(AdaptiveDetector(**args))
    else:
        raise ValueError(f"Unknown detector: {detector}")

    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()

    scene_seconds = [(s.get_seconds(), e.get_seconds()) for (s, e) in scene_list]
    return scene_seconds


@Pipeline.register_component(
    assigns="scene_intervals",
    depends=[],
    requires=[],
)
class DetectScene(Component):
    class Config:
        detector: str = "Content"
        threshold: float = None  # go with default
        merge_last_scene: float = True
        min_scene_len: str = "0.6s"

    def __call__(self, video, cfg):
        print(f"Processing {video.file_name}")

        json_path = Path("output") / f"{video.file_name}.scene_intervals.json"
        if json_path.exists():
            print(f"scene_inervals {video.file_name} exists")
            video.scene_intervals = json.loads(json_path.read_text())
            return video

        video.scene_intervals = get_scene_intervals(
            video, cfg.detector, cfg.threshold, cfg.merge_last_scene, cfg.min_scene_len
        )

        json_path.write_text(json.dumps(video.scene_intervals))
        return video
