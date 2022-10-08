from abc import ABC, abstractmethod, abstractproperty
from typing import List


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
        raise NotImplementedError('implement width')

    @abstractproperty
    def height(self):
        raise NotImplementedError('implement width')

    @abstractproperty
    def width_resolution(self):
        pass

    @abstractproperty
    def height_resolution(self):
        pass

    @abstractmethod
    def bounding_box(self):
        pass

    @abstractproperty
    def get_image_type(self):
        pass

    @abstractmethod
    def write(file_path):
        raise NotImplementedError('implement width')

    @abstractmethod
    def to_pil(self):
        raise NotImplementedError('implement width')


class Page(ABC):
    @abstractproperty
    def width(self):
        raise NotImplementedError('implement width')

    @abstractproperty
    def height(self):
        raise NotImplementedError('implement width')

    @abstractproperty
    def words(self):
        raise NotImplementedError('implement width')

    @abstractproperty
    def images(self):
        raise NotImplementedError('implement width')

    def has_one_large_image(self):
        def area(obj):
            return obj.width * obj.height

        return len(self.images) == 1 and area(self.images[0]) >= 0.9 * area(self)

    @abstractmethod
    def page_image(self, resolution):
        raise NotImplementedError('implement width')


class PDF(ABC):
    @abstractproperty
    def pages(self) -> List[Page]:
        raise NotImplementedError('implement __iter__ method')

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, idx):
        return self.pages[idx]

    def __iter__(self):
        return iter(self.pages)

    def get_iterator(self):
        return self.__iter__()
