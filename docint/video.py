from pathlib import Path
from typing import Any, Dict

from PIL import Image
from pydantic import BaseModel

from .audio import get_seconds
from .file import File


class Video(File):
    metadata: Dict[str, Any] = None

    class Config:
        extra = "allow"

    @classmethod
    def build(self, file_path):
        import cv2
        import numpy as np

        file_path = Path(file_path)
        return Video(_file_path=file_path)

    def to_json(self, exclude_defaults=True):
        return self.json(exclude_defaults=exclude_defaults, sort_keys=True, separators=(",", ":"))

    def to_disk(self, disk_file, format="json", exclude_defaults=True):
        disk_file = Path(disk_file)
        if format == "json":
            disk_file.write_text(self.to_json(exclude_defaults=exclude_defaults))
        else:
            raise NotImplementedError(f"Unknown format: {format}")

    def build_metadata(self):
        import cv2

        cap = cv2.VideoCapture(str(self.file_path))
        if not cap:
            raise IOError("Could not open file: {self.file_path}")

        self.metadata = {}
        self.metadata["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.metadata["frame_rate"] = cap.get(cv2.CAP_PROP_FPS)
        self.metadata["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.metadata["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.metadata["duration"] = self.metadata["frame_count"] / self.metadata["frame_rate"]

    @property
    def duration(self):
        if not self.metadata:
            self.build_metadata()
        return self.metadata["duration"]

    @property
    def width(self):
        if not self.metadata:
            self.build_metadata()
        return self.metadata["width"]

    @property
    def height(self):
        if not self.metadata:
            self.build_metadata()
        return self.metadata["height"]

    @property
    def size(self):
        return (self.width, self.height)

    @property
    def frame_rate(self):
        if not self.metadata:
            self.build_metadata()
        return self.metadata["frame_rate"]

    @property
    def frame_count(self):
        if not self.metadata:
            self.build_metadata()
        return self.metadata["frame_count"]

    @property
    def resolution(self):
        if not self.metadata:
            self.metadata = self.build_metadata()
        return self.metadata["width"] * self.metadata["height"]

    def get_frame(self, time_str):
        import cv2

        if not isinstance(time_str, (str, int, float)):
            raise ValueError(f"Time needs to be either str, float or int {type(time_str)}")

        secs = get_seconds(get_milli=True) if isinstance(time_str, str) else time_str

        frame_idx = int(self.frame_rate * secs)
        cap = cv2.VideoCapture(str(self.file_path))

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        success, frame = cap.read()

        # Check if frame was successfully read
        if success:
            # Convert the color from BGR to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Convert to PIL Image
            pil_image = Image.fromarray(frame)
            return pil_image
        else:
            raise IOError(f"Error: Could not read the frame[{frame_idx}] {self.file_path}")
