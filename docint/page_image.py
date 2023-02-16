import math
from base64 import b64encode  # noqa
from pathlib import Path

from PIL import Image
from pydantic import BaseModel

from .shape import Box, Coord, rotate_image_coord
from .util import get_full_path, is_repo_path


class ImageContext:
    def __init__(self, page_image):
        self.page_image = page_image
        self.image = None
        self.transformations = []

    def __enter__(self):
        image_path = Path(self.page_image.get_image_path())
        if image_path.exists():
            self.image = Image.open(image_path)
        else:
            # TODO THIS IS NEEDED FOR DOCKER, once directories
            # are properly arranged docker won't be needed.
            image_path = Path(".img") / image_path.parent.name / Path(image_path.name)
            print(image_path)
            self.image = Image.open(image_path)

        self.transformations = []
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        print("Closing Image Context")
        self.image.close()
        self.image = None
        self.transformations.clear()

    def normalize_angle(self, angle):
        return angle  # PIL2WAND

    def transform_rotate(self, image_coord, angle, prev_size, curr_size):
        angle_rad = math.radians(angle)

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
                angle = self.normalize_angle(angle)
                # image_coord = self.transform_rotate(image_coord, angle, prev_size, curr_size)
                image_coord = rotate_image_coord(image_coord, angle, prev_size, curr_size)
        return image_coord

    def inverse_transform(self, image_coord):
        print(f"\t>inverse_transform image_coord: {image_coord}")
        for trans_tuple in reversed(self.transformations):
            if trans_tuple[0] == "crop":
                top, bot = trans_tuple[1], trans_tuple[2]
                cur_w, cur_h = (bot.x - top.x), (bot.y - top.y)
                if not image_coord.inside(Coord(x=0, y=0), Coord(x=cur_w, y=cur_h)):
                    print(
                        f"\t\t !!!Failing coord: {image_coord} outside width:{cur_w}, height:{cur_h}]"
                    )
                    assert False, f"coord: {image_coord} outside [{cur_w}, {cur_h}]"
                    raise ValueError(f"coord: {image_coord} outside ({cur_w}, {cur_h})")
                image_coord = Coord(x=top.x + image_coord.x, y=top.y + image_coord.y)
                print(f"\t>inverse_crop image_coord: {image_coord}")
            else:
                angle, prev_size, curr_size = (
                    trans_tuple[1],
                    trans_tuple[2],
                    trans_tuple[3],
                )
                angle = self.normalize_angle(angle)
                # image_coord = self.transform_rotate(image_coord, -angle, curr_size, prev_size)
                image_coord = rotate_image_coord(image_coord, -angle, curr_size, prev_size)
                print(f"\t>inverse_rotate image_coord: {image_coord}")
        return image_coord

    def get_image_coord(self, doc_coord):
        image_coord = self.page_image.get_image_coord(doc_coord)
        return self.transform(image_coord)

    def get_doc_coord(self, image_coord):
        image_coord = self.inverse_transform(image_coord)
        return self.page_image.get_doc_coord(image_coord)

    def _image_rotate(self, angle, background):
        self.image = self.image.rotate(angle, expand=True, fillcolor=background)

    def rotate(self, angle, background="white"):
        angle = self.normalize_angle(angle)
        prev_size = (self.image.width, self.image.height)
        self._image_rotate(angle, background=background)
        curr_size = (self.image.width, self.image.height)
        print(f"\tRotate prev_size: {prev_size} curr_size: {curr_size} angle: {angle}")
        self.transformations.append(("rotate", angle, prev_size, curr_size))

    def _image_crop(self, img_top, img_bot):
        self.image = self.image.crop(  # PIL2WAND
            (
                round(img_top.x),
                round(img_top.y),
                round(img_bot.x),
                round(img_bot.y),
            )
        )

    def crop(self, top, bot):
        img_top, img_bot = self.get_image_coord(top), self.get_image_coord(bot)
        print(f"[{top},{bot}] -> [{img_top}, {img_bot}]")
        self._image_crop(img_top, img_bot)
        print(
            f"\tCrop top: {top} bot: {bot} img_top: {img_top} img_bot: {img_bot} Size: {self.image.size} width:{self.image.width} height:{self.image.height}"
        )
        self.transformations.append(("crop", img_top, img_bot))

    @property
    def size(self):
        return (self.image.width, self.image.height)

    @property
    def width(self):
        return self.image.width

    @property
    def height(self):
        return self.image.height

    @property
    def page_idx(self):
        return self.page_idx


class PageImage(BaseModel):
    image_width: float
    image_height: float
    image_path: str
    image_box: Box
    image_type: str
    page_width: float
    page_height: float

    @property
    def size(self):
        return (self.image_width, self.image_height)

    def get_image_coord(self, doc_coord):
        if self.image_type == "raster":
            image_x = round(doc_coord.x * self.image_width)
            image_y = round(doc_coord.y * self.image_height)
        else:
            page_x = round(doc_coord.x * self.page_width)
            page_y = round(doc_coord.y * self.page_height)

            image_x_scale = self.image_width / (self.image_box.bot.x - self.image_box.top.x)
            image_y_scale = self.image_height / (self.image_box.bot.y - self.image_box.top.y)

            image_x = round((page_x - self.image_box.top.x) * image_x_scale)
            image_y = round((page_y - self.image_box.top.y) * image_y_scale)

        image_x = min(max(0, image_x), self.image_width)
        image_y = min(max(0, image_y), self.image_height)

        image_coord = Coord(x=image_x, y=image_y)
        return image_coord

    def get_doc_coord(self, image_coord):
        # print(f'>get_doc_coord image_coord: {image_coord}')
        # print(f'>after_inv_trans image_coord: {image_coord}')

        page_x_scale = (self.image_box.bot.x - self.image_box.top.x) / self.image_width
        page_y_scale = (self.image_box.bot.y - self.image_box.top.y) / self.image_height

        page_x, page_y = image_coord.x * page_x_scale, image_coord.y * page_y_scale
        # ADDED THIS LATER <<<
        page_x, page_y = page_x + self.image_box.top.x, page_y + self.image_box.top.y
        doc_coord = Coord(x=page_x / self.page_width, y=page_y / self.page_height)
        return doc_coord

        # todo rotate

    def get_base64_image(self, top, bot, format="png", height=50):
        raise NotImplementedError("this is not implemented for PIL")

        # ThIS IS FOR WAND, NEED IT FOR PIL
        # img_top, img_bot = self.get_image_coord(top), self.get_image_coord(bot)
        # with self.image[
        #     int(img_top.x) : int(img_bot.x),
        #     int(img_top.y) : int(img_bot.y),  # noqa: E203
        # ] as cropped:
        #     if height:
        #         cw, ch = cropped.size
        #         width = int((cw * height) / ch)
        #         cropped.resize(width=width, height=height)

        #     img_bin = cropped.make_blob(format)
        #     img_str = f"data:image/{format};base64," + b64encode(img_bin).decode()
        # return img_str

    def get_image_path(self):
        if is_repo_path(self.image_path):
            image_path = get_full_path(self.image_path)
        else:
            print(self.image_path)
            image_path = self.image_path

        # moved the repo_path style

        # image_path = Path(self.image_path)
        # if not image_path.exists():
        #     # TODO THIS IS NEEDED FOR DOCKER, once directories
        #     # are properly arranged docker won't be needed.
        #     image_path = Path(".img") / image_path.parent.name / Path(image_path.name)

        return image_path

    def prepend_image_stub(self, stub):
        assert stub[-1] != "/"
        if is_repo_path(self.image_path):
            self.image_path = f"{stub}{self.image_path}"
        print(f"PREPEND image_path: {self.image_path}")

    def remove_image_stub(self, stub):
        assert stub[-1] != "/"
        if self.image_path.startswith(stub):
            self.image_path = self.image_path[len(stub) :]
            assert is_repo_path(self.image_path)
        print(f"REMOVE image_path: {self.image_path}")

    def to_pil_image(self, image_size=None):
        pil_image = Image.open(self.get_image_path())

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

        return pil_image
