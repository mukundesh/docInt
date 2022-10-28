import math
from base64 import b64encode
from pathlib import Path
from typing import Any, List, Tuple

from PIL import Image
from pydantic import BaseModel

from .shape import Box, Coord


class PageImage(BaseModel):
    image_width: float
    image_height: float
    image_path: str
    image_box: Box
    image_type: str
    page_width: float
    page_height: float
    image: Any = None
    transformations: List[Tuple] = []

    class Config:
        fields = {
            "page": {"exclude": True},
            "image": {"exclude": True},
            "transformations": {"exclude": True},
        }

    def transform_rotate(self, image_coord, angle, prev_size, curr_size):
        angle_rad = math.radians(angle)  # Edited when moved from Wand -> PIL

        prev_width, prev_height = prev_size
        curr_width, curr_height = curr_size

        image_x_centre, image_y_centre = prev_width / 2.0, prev_height / 2.0
        centre_x = image_coord.x - prev_width + image_x_centre
        centre_y = prev_height - image_coord.y - image_y_centre

        rota_centre_x = (centre_x * math.cos(angle_rad)) - (centre_y * math.sin(angle_rad))
        rota_centre_y = (centre_y * math.cos(angle_rad)) + (centre_x * math.sin(angle_rad))

        rota_image_x, rota_image_y = (
            rota_centre_x + curr_width / 2,
            curr_height / 2 - rota_centre_y,
        )

        rota_image_x = min(max(0, rota_image_x), curr_width)
        rota_image_y = min(max(0, rota_image_y), curr_height)
        image_coord = Coord(x=round(rota_image_x), y=round(rota_image_y))
        return image_coord

    def transform(self, image_coord):
        for trans_tuple in self.transformations:
            if trans_tuple[0] == "crop":
                top, bot = trans_tuple[1], trans_tuple[2]
                if not image_coord.inside(top, bot):
                    assert False, f"coord: {image_coord} outside [{top}, {bot}]"
                    raise ValueError(f"coord: {image_coord} outside crop_area [{top}, {bot}]")
                image_coord = Coord(x=image_coord.x - top.x, y=image_coord.y - top.y)
            elif trans_tuple[0] == "rotate":
                angle, prev_size, curr_size = (
                    trans_tuple[1],
                    trans_tuple[2],
                    trans_tuple[3],
                )
                image_coord = self.transform_rotate(image_coord, angle, prev_size, curr_size)
        return image_coord

    def inverse_transform(self, image_coord):
        # print(f'\t>inverse_transform image_coord: {image_coord}')
        for trans_tuple in reversed(self.transformations):
            if trans_tuple[0] == "crop":
                top, bot = trans_tuple[1], trans_tuple[2]
                cur_w, cur_h = (bot.x - top.x), (bot.y - top.y)
                if not image_coord.inside(Coord(x=0, y=0), Coord(x=cur_w, y=cur_h)):
                    assert False, f"coord: {image_coord} outside [{cur_w}, {cur_h}]"
                    raise ValueError(f"coord: {image_coord} outside [{cur_w}, {cur_h}]")
                image_coord = Coord(x=top.x + image_coord.x, y=top.y + image_coord.y)
                # print(f'\t>inverse_crop image_coord: {image_coord}')
            else:
                angle, prev_size, curr_size = (
                    trans_tuple[1],
                    trans_tuple[2],
                    trans_tuple[3],
                )
                image_coord = self.transform_rotate(image_coord, -angle, curr_size, prev_size)
                # print(f'\t>inverse_rotate image_coord: {image_coord}')
        return image_coord

    def get_image_coord(self, doc_coord):
        page_x = round(doc_coord.x * self.page_width)
        page_y = round(doc_coord.y * self.page_height)

        image_x_scale = self.image_width / (self.image_box.bot.x - self.image_box.top.x)
        image_y_scale = self.image_height / (self.image_box.bot.y - self.image_box.top.y)

        image_x = round((page_x - self.image_box.top.x) * image_x_scale)
        image_y = round((page_y - self.image_box.top.y) * image_y_scale)

        image_x = min(max(0, image_x), self.image_width)
        image_y = min(max(0, image_y), self.image_height)

        image_coord = self.transform(Coord(x=image_x, y=image_y))
        return image_coord

    def get_doc_coord(self, image_coord):
        # print(f'>get_doc_coord image_coord: {image_coord}')
        image_coord = self.inverse_transform(image_coord)
        # print(f'>after_inv_trans image_coord: {image_coord}')

        page_x_scale = (self.image_box.bot.x - self.image_box.top.x) / self.image_width
        page_y_scale = (self.image_box.bot.y - self.image_box.top.y) / self.image_height

        page_x, page_y = image_coord.x * page_x_scale, image_coord.y * page_y_scale
        # ADDED THIS LATER <<<
        page_x, page_y = page_x + self.image_box.top.x, page_y + self.image_box.top.y
        doc_coord = Coord(x=page_x / self.page_width, y=page_y / self.page_height)
        return doc_coord

    def _init_image(self):
        print(f"INITIALIZING IMAGE {self.image_path}")
        if self.image is None:
            self.image_path = Path(self.image_path)
            if self.image_path.exists():
                self.image = Image.open(self.image_path)
            else:
                # TODO THIS IS NEEDED FOR DOCKER, once directories
                # are properly arranged docker won't be needed.
                image_path = Path(".img") / self.image_path.parent.name / Path(self.image_path.name)
                print(image_path)
                self.image = Image.open(image_path)

    def get_skew_angle(self, orientation):
        return 0.0

    #     self._init_image()
    #     if orientation == "h":
    #         hor_image = self.image.clone()
    #         hor_image.deskew(0.8 * self.image.quantum_range)
    #         angle = float(hor_image.artifacts["deskew:angle"])
    #     else:
    #         ver_image = self.image.clone()
    #         ver_image.rotate(90)
    #         ver_image.deskew(0.8 * ver_image.quantum_range)
    #         angle = float(ver_image.artifacts["deskew:angle"])
    #     return angle

    def rotate(self, angle, background="white"):
        if not self.image:
            self._init_image()

        prev_size = (self.image.width, self.image.height)
        self.image = self.image.rotate(angle, expand=True, fillcolor=background)
        curr_size = (self.image.width, self.image.height)
        print(f"\tRotate prev_size: {prev_size} curr_size: {curr_size} angle: {angle}")
        self.transformations.append(("rotate", angle, prev_size, curr_size))

    def crop(self, top, bot):
        if not self.image:
            self._init_image()
        img_top, img_bot = self.get_image_coord(top), self.get_image_coord(bot)
        print(f"[{top},{bot}] -> [{img_top}, {img_bot}]")
        self.image = self.image.crop(
            (
                round(img_top.x),
                round(img_top.y),
                round(img_bot.x),
                round(img_bot.y),
            )
        )

        # print(f'\tCrop top: {top} bot: {bot} img_top: {img_top} img_bot: {img_bot}')
        self.transformations.append(("crop", img_top, img_bot))

        # todo rotate

    def get_base64_image(self, top, bot, format="png", height=50):
        if not self.image:
            self._init_image()

        img_top, img_bot = self.get_image_coord(top), self.get_image_coord(bot)
        with self.image[
            int(img_top.x) : int(img_bot.x),
            int(img_top.y) : int(img_bot.y),  # noqa: E203
        ] as cropped:
            if height:
                cw, ch = cropped.size
                width = int((cw * height) / ch)
                cropped.resize(width=width, height=height)

            img_bin = cropped.make_blob(format)
            img_str = f"data:image/{format};base64," + b64encode(img_bin).decode()
        return img_str

    def clear_transforms(self):
        if self.image:
            self.image.close()
            self.image = None
        self.transformations.clear()

    @property
    def curr_size(self):
        if self.image is not None:
            return self.image.width, self.image.height
        else:
            return self.image_width, self.image_height

    def to_pil_image(self, image_size=None):
        if not self.image:
            self._init_image()

        pil_image = self.image

        if image_size:
            if image_size[0] and image_size[1]:
                pil_image = pil_image.resize(image_size)
            else:
                (cur_width, cur_height) = pil_image.size
                if image_size[0]:
                    scale = image_size[0] / cur_width
                    pil_image = pil_image.resize((image_size[0], int(cur_height * scale)))
                else:
                    scale = image_size[1] / cur_height
                    pil_image = pil_image.resize((int(cur_width * scale), image_size[1]))
            self.image.close()
            self.image = None  # close the image to conserve memory

        return pil_image
