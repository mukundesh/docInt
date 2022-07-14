from collections import Counter
from pathlib import Path

from PIL import Image

from ..shape import Coord
from ..vision import Vision

# import subprocess


@Vision.factory("orient_pages", default_config={"min_word_len": 4, "images_dir": None})
class OrientPage:
    def __init__(self, min_word_len, images_dir):
        self.min_word_len = min_word_len
        self.images_dir = Path(images_dir)

    def needs_reorientation(self, page):
        horz_score = sum([1 if w.box.is_horz else 0 for w in page.words])
        return True if horz_score < (len(page.words) / 2.0) else False

    def get_reorient_angle(self, page):
        long_words = [w for w in page.words if len(w) > self.min_word_len]

        angleDict = {
            (0, 1, 3, 2): 0,
            (1, 0, 2, 3): 0,
            (1, 0, 3, 2): 0,
            (0, 1, 2, 3): 0,
            (3, 0, 2, 1): 90,
            (0, 3, 1, 2): 90,
            (0, 3, 2, 1): 90,
            (3, 0, 1, 2): 90,
            (2, 3, 1, 0): 180,
            (3, 2, 1, 0): 180,
            (3, 2, 0, 1): 180,
            (2, 3, 0, 1): 180,
            (1, 2, 0, 3): 270,
            (1, 2, 3, 0): 270,
            (2, 1, 3, 0): 270,
            (2, 1, 0, 3): 270,
        }
        angle_counter = Counter()
        for w in long_words:
            wCoordIdxs = list(enumerate(w.coords))
            wCoordIdxs.sort(key=lambda tup: (tup[1].y, tup[1].x))
            idxs = tuple([tup[0] for tup in wCoordIdxs])
            if tuple(idxs) not in angleDict:
                print(f"idx: {w.page_idx} {w.word_idx} -> {idxs}")
                assert False
            else:
                angle = angleDict[tuple(idxs)]
            angle_counter[angle] += 1
        return max(angle_counter, key=angle_counter.get)

    def orient_image(self, img_path, angle):
        assert angle in (90, 180, 270)
        new_path = img_path.parent / (img_path.stem + f"-r{angle}" + img_path.suffix)
        if not new_path.exists():
            print(f"rotating the image {new_path}")
            img = Image.open(img_path).rotate(angle)
            img.save(new_path)

    def orient_page(self, page, angle):
        xMultiplier = (page.height / float(page.width)) if angle in (90, 270) else 1.0
        yMultiplier = (page.width / float(page.height)) if angle in (90, 270) else 1.0

        def updateCoord(coord, angle, xoffset, yoffset):
            x, y, a = coord.x, coord.y, angle
            # TODO FIX THIS
            newX = y - xoffset if a == 90 else 1 - y - xoffset if a == 270 else 1 - x
            newY = 1 - x + yoffset if a == 90 else x + yoffset if a == 270 else 1 - y

            newX, newY = newX * xMultiplier, newY * yMultiplier
            newX, newY = min(max(newX, 0.0), 1.0), min(max(newY, 0.0), 1.0)
            return Coord(x=newX, y=newY)

        def updateCoords(word, angle, w, h):
            xoffset = (1.0 - (w / float(h))) / 2.0
            yoffset = ((float(h) / w) - 1.0) / 2.0
            newCoords = [updateCoord(c, angle, xoffset, yoffset) for c in word.coords]
            word.update_coords(newCoords)

        [updateCoords(w, angle, page.width, page.height) for w in page.words]

    def __call__(self, doc):
        print(f"Processing {doc.pdf_name}")
        doc.add_extra_page_field("reoriented_angle", ("noparse", "", ""))
        for page in doc.pages:
            angle = self.get_reorient_angle(page)
            print(f"page_idx: {page.page_idx} Angle: {angle}")
            if angle != 0:
                print(f"Orienting page_idx: {page.page_idx}")
                angle = self.get_reorient_angle(page)
                self.orient_page(page, angle)
                page.reoriented_angle = angle
                if self.images_dir:
                    img_filename = Path(f"orig-{page.page_idx+1:03d}-000.png")
                    img_path = self.images_dir / doc.pdf_stem / img_filename
                    self.orient_image(img_path, angle)
            else:
                page.reoriented_angle = 0
        return doc
