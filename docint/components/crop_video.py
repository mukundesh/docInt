import json
import subprocess
from pathlib import Path

from ..ppln import Component, Pipeline


# TODO this bounding box should be a shape
def crop_video(video, bounding_box, crop_video_file):
    # ffmpeg -i output.mp4 -filter:v "crop=1280:35:0:658" output-crop.mp4
    print(bounding_box)
    [x0, y0, x1, y1] = bounding_box

    (video_width, video_height) = video.size

    c_w, c_h = int((x1 - x0) * video_width), int((y1 - y0) * video_height)
    c_x0, c_y0 = int(x0 * video_width), int(y0 * video_height)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video.file_path),
        "-filter:v",
        f"crop={c_w}:{c_h}:{c_x0}:{c_y0}",
        str(crop_video_file),
    ]

    # cmd = [
    #     "ffmpeg",
    #     "-y",
    #     "-i",
    #     str(video.file_path),
    #     "-ss",
    #     str(10),
    #     "-to",
    #     str(40),
    #     "-vf",
    #     f'crop={c_w}:{c_h}:{c_x0}:{c_y0}',
    #     str(crop_video_file),
    # ]

    print(" ".join(cmd))
    subprocess.check_call(cmd, stderr=subprocess.DEVNULL)


def convert_bbox(bbox, image_size):
    (w, h) = image_size
    return [round(bbox[0] * w), round(bbox[1] * h), round(bbox[2] * w), round(bbox[3] * h)]


@Pipeline.register_component(
    assigns="crop_file_path",
    depends=[],
    requires=[],
)
class CropVideo(Component):
    class Config:
        bbox = [float]
        name_stub = str

    def __call__(self, video, cfg):
        print(f"Processing {video.file_name}")

        json_path = Path("output") / f"{video.file_name}.crop_file_path.json"
        crop_file_path = Path("output") / f"{video.file_name}.crop_{cfg.name_stub}.mp4"

        if json_path.exists() and crop_file_path.exists():
            video.crop_file_path = json.loads(json_path.read_text())
            return video

        crop_video(video, cfg.bbox, crop_file_path)
        video.crop_file_path = str(crop_file_path)
        json_path.write_text(json.dumps(str(crop_file_path)))
        return video
