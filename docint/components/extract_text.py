import json
from collections import Counter
from itertools import groupby
from operator import itemgetter
from pathlib import Path
from typing import Any, Dict

from PIL import Image

from ..ppln import Component, Pipeline


def get_time_str(time_secs):
    hr = 0 if time_secs < 3600 else int(time_secs / 3600)
    time_secs = time_secs - (hr * 3600)

    mn = 0 if time_secs < 60 else int(time_secs / 60)
    time_secs = time_secs - (mn * 60)

    ss = int(time_secs)
    return f"{hr:02d}:{mn:02d}:{ss:02d}"


def get_avg_color(cropped_img):
    color_img = cropped_img.crop([10, 0, 20, 10])
    color_counts = color_img.getcolors(100)
    r, g, b = (
        sum(c[1][0] for c in color_counts),
        sum(c[1][1] for c in color_counts),
        sum(c[1][2] for c in color_counts),
    )
    return (int(r / 100), int(g / 100), int(b / 100))


def get_interval_texts(video, bbox, gap, is_ticker):
    def is_valid_text(text):
        return True if len(text) > 10 else False

    def remove_duplicates(interval_texts):
        result = []
        for k, group in groupby(interval_texts, key=itemgetter(1)):
            group = list(group)
            time_range = (group[0][0], group[-1][0])
            print(f"{time_range} {k}")
            result.append((time_range, k))
        return result

    import pytesseract

    time_idx, duration = 0, video.duration
    interval_texts = []

    while time_idx < duration:
        frame_img = video.get_frame(time_idx)
        cropped_img = frame_img.crop(bbox)
        try:
            osd = pytesseract.image_to_osd(
                cropped_img, config="-c min_characters_to_try=5", output_type="dict"
            )
        except pytesseract.pytesseract.TesseractError as e:  # noqa
            osd = {"script": "UNKNOWN", "script_conf": 0.0}

        config_str = ""
        # config_str = '--psm 7'
        if osd["script"] in ("Devanagari", "Arabic", "Hangul"):
            cropped_text = pytesseract.image_to_string(cropped_img, config=config_str, lang="hin")
        else:
            cropped_text = pytesseract.image_to_string(cropped_img, config=config_str)

        cropped_text = cropped_text.strip("\n -_~|'\"—.‘“").replace("\n", " ").replace("‘", "")

        time_str = get_time_str(time_idx)
        avg_color = get_avg_color(cropped_img)

        if is_valid_text(cropped_text):
            print(f'{time_str}: {cropped_text} {osd["script"]} {osd["script_conf"]} {avg_color}')
            interval_texts.append((time_idx, cropped_text))
        else:
            print(
                f'{time_str}: INVALID >{cropped_text}< {osd["script"]} {osd["script_conf"]} {avg_color}'
            )

        time_idx += gap
    interval_texts = remove_duplicates(interval_texts)
    return interval_texts


def get_frame_text(frame_img, bbox):
    import pytesseract

    cropped_img = frame_img.crop(bbox)
    try:
        osd = pytesseract.image_to_osd(
            cropped_img, config="-c min_characters_to_try=5", output_type="dict"
        )
    except pytesseract.pytesseract.TesseractError as e:  # noqa
        osd = {"script": "UNKNOWN", "script_conf": 0.0}

    config_str = ""
    # config_str = '--psm 7'

    if osd["script"] in ("Latin", "Cyrillic"):
        cropped_text = pytesseract.image_to_string(cropped_img, config=config_str)
        cropped_text = cropped_text.strip("\n -_~|'\"—.‘“").replace("\n", " ").replace("‘", "")
        if len(cropped_text) > 10:
            return cropped_text
    elif osd["script"] in ("Devanagari", "Arabic", "Hangul"):
        cropped_text = pytesseract.image_to_string(cropped_img, config=config_str, lang="hin")
        cropped_text = cropped_text.strip("\n -_~|'\"—.‘“").replace("\n", " ").replace("‘", "")
        if len(cropped_text) > 10:
            return cropped_text
    return None


ImagehashCutoff = 3


def match_image_hash(frame_img, hash_bbox, match_hash):
    import imagehash

    return match_hash - imagehash.colorhash(frame_img.crop(hash_bbox)) > ImagehashCutoff


def get_scene_text_two_pass(video, start_ss, end_ss, bbox, gap, hash_bbox, match_hash):
    gap1 = 10 * gap
    gap2 = gap

    assert gap1 > gap2, f"incorrect values of gaps {gap1} {gap2}"

    def iter_pass1(start_ss, end_ss, gap1):
        t_idx = start_ss
        while t_idx < end_ss:
            yield t_idx
            t_idx += gap1

    def iter_pass2(start_ss, end_ss, gap1, gap2, first_pass_timeidxs):
        t_idx = start_ss
        for f_idx in first_pass_timeidxs:
            f_start_idx, f_end_idx = f_idx - gap1, f_idx + gap2

            t_idx = max(t_idx, f_start_idx)
            while t_idx < min(end_ss, f_end_idx):
                yield t_idx
                t_idx += gap2

    second_pass_timeidxs, time_idx_texts = [], {}
    for time_idx in iter_pass1(start_ss, end_ss, gap1):
        frame_img = video.get_frame(time_idx)

        if not match_image_hash(frame_img, hash_bbox, match_hash):
            continue

        frame_text = get_frame_text(frame_img, bbox)
        if frame_text:
            print(f"\t{get_time_str(time_idx)}: {frame_text}")
            second_pass_timeidxs.append(time_idx)
            time_idx_texts[time_idx] = frame_text
        else:
            print(f"\t{get_time_str(time_idx)}")

    if not second_pass_timeidxs and (end_ss - start_ss) < 10:
        print("\tEmpty- Adding start")
        second_pass_timeidxs.append(start_ss)

    print("\tPhase II")
    cropped_texts = []
    for time_idx in iter_pass2(start_ss, end_ss, gap1, gap2, second_pass_timeidxs):
        # print(f'\t{time_idx}')
        frame_text = time_idx_texts.get(time_idx, None)
        if not frame_text:
            frame_img = video.get_frame(time_idx)
            frame_text = get_frame_text(frame_img, bbox)

        if frame_text:
            print(f"\t{get_time_str(time_idx)}: {frame_text}")
            cropped_texts.append(frame_text)
        else:
            print(f"\t{get_time_str(time_idx)}")
    cropped_texts.sort(key=len, reverse=True)  # prefer longer text over shorter
    return max(c := Counter(cropped_texts), key=c.get) if cropped_texts else "NO_NAME"


def get_scene_text(video, start_ss, end_ss, bbox, gap):
    import pytesseract

    time_idx = start_ss
    cropped_texts = []

    while time_idx < end_ss:
        frame_img = video.get_frame(time_idx)
        cropped_img = frame_img.crop(bbox)
        try:
            osd = pytesseract.image_to_osd(
                cropped_img, config="-c min_characters_to_try=5", output_type="dict"
            )
        except pytesseract.pytesseract.TesseractError as e:  # noqa
            osd = {"script": "UNKNOWN", "script_conf": 0.0}

        config_str = ""
        # config_str = '--psm 7'

        if osd["script"] in ("Latin", "Cyrillic"):
            cropped_text = pytesseract.image_to_string(cropped_img, config=config_str)
            cropped_text = cropped_text.strip("\n -_~|'\"—.‘“").replace("\n", " ").replace("‘", "")
            if len(cropped_text) > 10:
                cropped_texts.append(cropped_text)
        time_idx += gap

    return max(c := Counter(cropped_texts), key=c.get) if cropped_texts else "NO_NAME"


def convert_bbox(bbox, image_size):
    (w, h) = image_size
    return [round(bbox[0] * w), round(bbox[1] * h), round(bbox[2] * w), round(bbox[3] * h)]


@Pipeline.register_component(
    assigns="scene_texts",
    depends=[],
    requires=[],
)
class ExtractText(Component):
    class Config:
        text_configs = [Dict[str, Any]]

    # def __call__(self, video, cfg):
    #     print(f"Processing {video.file_name}")
    #     for t_cfg in cfg.text_configs:
    #         bbox, gap, is_ticker = t_cfg["bbox"], t_cfg["gap"], t_cfg["is_ticker"]
    #         img_bbox = convert_bbox(bbox, video.size)
    #         interval_texts = get_interval_texts(video, img_bbox, gap, is_ticker)
    #         video[t_cfg['name']] = interval_texts
    #     return video

    def __call__(self, video, cfg):
        print(f"Processing {video.file_name}")
        json_path = Path("output") / f"{video.file_name}.scene_texts.json"
        if json_path.exists():
            print(f"scene_texts {video.file_name} exists")
            video.scene_texts = json.loads(json_path.read_text())
            return video

        video.scene_texts = {}
        for t_cfg in cfg.text_configs:
            bbox, gap = t_cfg["bbox"], t_cfg["gap"]
            img_bbox = convert_bbox(bbox, video.size)
            scene_texts, merged_scene_texts = [], []
            for s, e in video.scene_list:
                scene_text = get_scene_text_two_pass(video, s, e, img_bbox, gap)
                print(f"{get_time_str(s)}->{get_time_str(e)} {scene_text}")
                scene_texts.append(((s, e), scene_text))

            print("Merging Scenes")
            for text, group in groupby(scene_texts, key=itemgetter(1)):
                group = list(group)
                s, e = (group[0][0][0], group[-1][0][1])
                merged_scene_texts.append(((s, e), text))
                print(f"{get_time_str(s)}->{get_time_str(e)} {text}")

            video.scene_texts[t_cfg["name"]] = merged_scene_texts

        json_path.write_text(json.dumps(video.scene_texts))
        return video
