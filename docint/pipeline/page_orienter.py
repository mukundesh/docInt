from collections import Counter

from ..vision import Vision
from ..page import Page
from ..shape import Coord, Poly


@Vision.component("orient_pages", default_config={"min_word_len": 4})
class OrientPage:
    def __init__(self, min_word_len):
        self.min_word_len = min_word_len
        if not Page.has_extension("reoriented_angle"):
            Page.set_extension("reoriented_angle", default=0, type_hint=int)

    def needs_reorientation(self, page):
        horzScore = [1 if w.box.is_horizontal else 0 for w in page]
        return True if horzScore > len(page) / 2.0 else False

    def get_reorient_angle(self, page):
        long_words = [w for w in page if len(w) > self.min_word_len]

        angleDict = {
            (0, 1, 3, 2): 0,
            (1, 0, 2, 3): 0,
            (1, 0, 3, 2): 0,
            (3, 0, 2, 1): 90,
            (2, 3, 1, 0): 180,
            (1, 2, 0, 3): 270,
        }
        angle_counter = Counter()
        for w in long_words:
            wCoordIdxs = list(enumerate(w.coords))
            wCoordIdxs.sort(key=lambda tup: (tup[1].y, tup[1].x))
            idxs = [tup[0] for tup in wCoordIdxs]
            angle = angleDict[idxs]
            angle_counter[angle] += 1
        return max(angle_counter, key=angle_counter.get)

    def orient_page(page, angle):
        xMultiplier = (page.height / float(page.width)) if angle in (90, 270) else 1.0
        yMultiplier = (page.width / float(page.height)) if angle in (90, 270) else 1.0

        def updateCoord(coord, angle, xoffset, yoffset):
            x, y, a = coord.x, coord.y, angle
            # TODO FIX THIS
            newX = y - offset if a == 90 else 1 - y - offset if a == 270 else 1 - x
            newY = 1 - x + offset if a == 90 else x + offset if a == 270 else 1 - y

            newX, newY = newX * xMultiplier, newY * yMultiplier
            return Coord(newX, newY)

        def updateCoords(word, angle, w, h):
            xoffset = (1.0 - (w / float(h))) / 2.0
            yoffset = ((float(h) / w) - 1.0) / 2.0
            newCoords = [updateCoord(c, angle, xoffset, yoffset) for c in word.coords]
            word.coords = newCoords

        [updateCoord(w, angle, page.wt, page.ht) for w in page]

    def __call__(self, doc):
        for page in doc.pages:
            if self.needs_reorientation(page):
                angle = self.get_reorient_angle(page)
                self.orient_page(page, angle)
                page._.reoriented_angle = angle
            else:
                page._.reoriented_angle = 0
