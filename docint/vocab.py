from operator import itemgetter

from polyleven import levenshtein


class Vocab:
    def __init__(self, texts, *, case_sensitive=False):
        self.case_sensitive = case_sensitive
        if self.case_sensitive:
            self._texts = set(texts)
        else:
            self._texts = set(t.lower() for t in texts)

    def __contains__(self, text):
        text = text if self.case_sensitive else text.lower()
        return text in self._texts

    def has_text(self, text, dist_cutoff=0):
        def similar(t1, t2):
            return levenshtein(t1, t2, dist_cutoff) <= dist_cutoff

        text = text if self.case_sensitive else text.lower()
        if dist_cutoff == 0:
            return text in self._texts
        else:
            if text in self._texts:
                return True

            return any(t for t in self._texts if similar(text, t))

    def find_texts(self, text, dist_cutoff=0):
        text = text if self.case_sensitive else text.lower()

        if dist_cutoff == 0:
            return [(text, 0)] if text in self._texts else []
        else:
            # if text in self._texts:
            #    return [(text, 0)]

            result = []
            for t in self._texts:
                dist = levenshtein(text, t)
                if dist <= dist_cutoff:
                    result.append((t, dist))
            return sorted(result, key=itemgetter(1))
