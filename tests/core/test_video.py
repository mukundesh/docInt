from pathlib import Path

import pytest

from docint.video import Video


def test_video_properties(small_video_path):
    video = Video.build(small_video_path)
    assert round(video.duration, 1) == 1.6
    assert video.frame_count == 47
    assert abs(video.frame_rate - 29.97002997002997) < 0.001
    assert video.width == 1920
    assert video.height == 1080


def test_frame_image(small_video_path):
    video = Video.build(small_video_path)

    frame_pil = video.get_frame(1)
    assert frame_pil.size == (1920, 1080)
