from abc import ABC, abstractmethod, abstractproperty
from typing import List


class Char(ABC):
    @abstractproperty
    def text(self):
        pass

    @abstractproperty
    def bounding_box(self):
        pass


class Word(ABC):
    @abstractproperty
    def text(self):
        pass

    @abstractproperty
    def bounding_box(self):
        pass


class Image(ABC):
    @abstractproperty
    def width(self):
        raise NotImplementedError("implement width")

    @abstractproperty
    def height(self):
        raise NotImplementedError("implement width")

    @abstractproperty
    def horizontal_dpi(self):
        pass

    @abstractproperty
    def vertical_dpi(self):
        pass

    @abstractmethod
    def bounding_box(self):
        pass

    @abstractproperty
    def get_image_type(self):
        pass

    @abstractmethod
    def save(file_path):
        raise NotImplementedError("implement width")

    @abstractmethod
    def to_pil(self):
        raise NotImplementedError("implement width")


class Page(ABC):
    @abstractproperty
    def width(self):
        raise NotImplementedError("implement width")

    @abstractproperty
    def height(self):
        raise NotImplementedError("implement width")

    @abstractproperty
    def words(self):
        raise NotImplementedError("implement width")

    @abstractproperty
    def chars(self):
        raise NotImplementedError("implement width")

    @abstractproperty
    def images(self):
        raise NotImplementedError("implement width")

    @abstractproperty
    def rotation(self):
        raise NotImplementedError("implement width")

    @property
    def has_one_large_image(self):
        def area(obj):
            return obj.width * obj.height

        return len(self.images) == 1 and area(self.images[0]) >= 0.9 * area(self)

    @abstractmethod
    def page_image_to_pil(self, *, dpi=None):
        raise NotImplementedError("implement width")

    @abstractmethod
    def page_image_save(self, file_path, *, dpi=None):
        pass


class PDF(ABC):
    @abstractproperty
    def pages(self) -> List[Page]:
        raise NotImplementedError("implement __iter__ method")

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, idx):
        return self.pages[idx]

    def __iter__(self):
        return iter(self.pages)

    def get_iterator(self):
        return self.__iter__()

    def get_info(self):
        page_infos = []
        for page in self.pages:
            width, height, words, images = (
                page.width,
                page.height,
                page.words,
                page.images,
            )
            page_info = {
                "width": width,
                "height": height,
                "num_words": len(words),
                "num_images": len(images),
            }
            page_info["has_one_large_image"] = page.has_one_large_image

            image_infos = []
            for image in page.images:
                image_infos.append(
                    {
                        "width": image.width,
                        "height": image.height,
                        "bounding_box": list(image.bounding_box),
                    }
                )
            page_info["image_infos"] = image_infos
            page_infos.append(page_info)
        return {"page_infos": page_infos}
