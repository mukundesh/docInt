import gzip
import mimetypes
import subprocess
from pathlib import Path
from typing import Any, List, Tuple

from pydantic import BaseModel
from pydub import AudioSegment
from pydub.utils import mediainfo

from .file import File


class AudioWord(BaseModel):
    word_idx: int
    text_: str
    start_ms: int
    end_ms: int
    audio: Any = None
    chunk_idx: int

    class Config:
        fields = {
            "audio": {"exclude": True},
        }


def get_seconds(time_str):
    if not isinstance(time_str, str):
        return time_str

    hrs, mins, secs = time_str.split(":", 2)
    return (int(hrs) * 60 * 60) + (int(mins) * 60) + int(secs)


class Audio(File):
    words: List[Any] = []
    audio_seg: Any = None
    audio_metadata: Any = None
    rm_intervals: List[Tuple[int, int]] = []

    class Config:
        fields = {
            "audio_seg": {"exclude": True},
            "audio_metadata": {"exclude": True},
        }
        extra = "allow"

    def __getitem__(self, idx):
        return self.words[idx]

    @classmethod
    def build(self, file_path):
        file_path = Path(file_path)
        return Audio(_file_path=file_path)

    @classmethod
    def load_audio(self):
        if self.file_path.suffix.lower() == ".mp3":
            self.audio_seg = AudioSegment.from_mp3(self.file_path)
        else:
            self.audio_seg = AudioSegment.from_file(self.file_path)

    @property
    def mime_type(self):
        if self.file_path.suffix.lower() == ".webm":
            return "audio/webm"
        else:
            return mimetypes.guess_type(self.file_name)[0]

    @property
    def format(self):
        return self.file_path.suffix.strip(".").lower()

    @property
    def metadata(self):
        if not self.audio_metadata:
            self.audio_metadata = mediainfo(self.file_path)
        return self.audio_metadata

    @property
    def num_channels(self):
        return int(self.metadata["channels"])

    @property
    def frame_rate(self):
        return int(self.metadata["avg_frame_rate"])

    @property
    def sample_rate(self):
        return int(self.metadata["sample_rate"])

    @property
    def dBFS(self):
        return self.audio_seg.dBFS

    def get_trimmed_audio(self):
        audio_intervals, prev_start = [], 0
        for (s, e) in self.rm_intervals:
            audio_intervals.append(self.audio_seg[prev_start : s * 1000])
            prev_start = e * 1000
        audio_intervals.append(self.audio_seg[prev_start : len(self.audio_seg)])
        return sum(audio_intervals)

    def get_bytes(self, format=None, frame_rate=None, rm_intervals=True):
        if not self.audio_seg:
            self.load_audio()

        if not format:
            format = self.format

        if rm_intervals:
            trimmed_segment = self.get_trimmed_audio()

            if frame_rate:
                trimmed_segment = trimmed_segment.set_frame_rate(frame_rate)

            return trimmed_segment.export(format=format).read()
        else:
            to_export = self.audio_seg.set_frame_rate(frame_rate) if frame_rate else self.audio_seg
            return to_export.export(format=format).read()

    @property
    def duration(self):
        total_interval_len = sum(e - s for (s, e) in self.rm_intervals)

        return int(int(float(self.metadata["duration"])) - total_interval_len)

    def to_json(self, exclude_defaults=True):
        return self.json(exclude_defaults=exclude_defaults, sort_keys=True, separators=(",", ":"))

    def to_disk(self, disk_file, format="json", exclude_defaults=True):
        disk_file = Path(disk_file)
        if format == "json":
            if disk_file.suffix.lower() in (".gz"):
                with gzip.open(disk_file, "wb") as f:
                    f.write(
                        bytes(self.to_json(exclude_defaults=exclude_defaults), encoding="utf-8")
                    )
            else:
                disk_file.write_text(self.to_json(exclude_defaults=exclude_defaults))
        else:
            raise NotImplementedError(f"Unknown format: {format}")
            # disk_file.write_bytes(self.to_msgpack())

    def split(self, start_secs, end_secs, input_dir):
        # ffmpeg -i source.m4v -ss       0 -t  593.3 -c copy part1.m4v

        split_file = input_dir / f"{self.file_stem}+{start_secs}-{end_secs}{self.file_suffix}"
        cmd = [
            "ffmpeg",
            "-i",
            str(self.file_path),
            "-ss",
            str(start_secs),
            "-t",
            str(end_secs - start_secs),
            "-c",
            "copy",
            str(split_file),
        ]
        print(cmd)
        subprocess.check_call(cmd)
        return Audio.build(split_file)


"""
{
  u'DISPOSITION': {
    u'attached_pic': u'0',
    u'clean_effects': u'0',
    u'comment': u'0',
    u'default': u'0',
    u'dub': u'0',
    u'forced': u'0',
    u'hearing_impaired': u'0',
    u'karaoke': u'0',
    u'lyrics': u'0',
    u'original': u'0',
    u'visual_impaired': u'0'
  },
  u'TAG': {u'encoder': u'Lavf55.12.100'},
  u'avg_frame_rate': u'0/0',
  u'bit_rate': u'96179',
  u'bits_per_sample': u'0',
  u'channel_layout': u'stereo',
  u'channels': u'2',
  u'codec_long_name': u'MP3 (MPEG audio layer 3)',
  u'codec_name': u'mp3',
  u'codec_tag': u'0x0000',
  u'codec_tag_string': u'[0][0][0][0]',
  u'codec_time_base': u'1/32000',
  u'codec_type': u'audio',
  u'duration': u'10.044000',
  u'duration_ts': u'141740928',
  u'filename': u'/Users/jiaaro/Documents/code/pydub/test/data/test1.mp3',
  u'format_long_name': u'MP2/3 (MPEG audio layer 2/3)',
  u'format_name': u'mp3',
  u'id': u'N/A',
  u'index': u'0',
  u'max_bit_rate': u'N/A',
  u'nb_frames': u'N/A',
  u'nb_programs': u'0',
  u'nb_read_frames': u'N/A',
  u'nb_read_packets': u'N/A',
  u'nb_streams': u'1',
  u'probe_score': u'51',
  u'profile': u'unknown',
  u'r_frame_rate': u'0/0',
  u'sample_fmt': u's16p',
  u'sample_rate': u'32000',
  u'size': u'120753',
  u'start_pts': u'487305',
  u'start_time': u'0.034531',
  u'time_base': u'1/14112000'
}

"""
