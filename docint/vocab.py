from operator import itemgetter


class Vocab:
    def __init__(self, texts, *, case_sensitive=False):
        from polyleven import levenshtein

        self.case_sensitive = case_sensitive

        # order of words is important, hence storing in dict (py >=3.7)
        if self.case_sensitive:
            self._texts = dict((t, None) for t in texts)
        else:
            self._texts = dict((t.lower(), None) for t in texts)

    def __contains__(self, text):
        text = text if self.case_sensitive else text.lower()
        return text in self._texts

    def has_text(self, text, dist_cutoff=0):
        from polyleven import levenshtein  # noqa

        def similar(t1, t2):
            return levenshtein(t1, t2, dist_cutoff) <= dist_cutoff  # noqa

        text = text if self.case_sensitive else text.lower()
        if dist_cutoff == 0:
            return text in self._texts
        else:
            if text in self._texts:
                return True

            return any(t for t in self._texts if similar(text, t))

    def find_texts(self, text, dist_cutoff=0):
        from polyleven import levenshtein  # noqa

        text = text if self.case_sensitive else text.lower()

        if dist_cutoff == 0:
            return [(text, 0)] if text in self._texts else []
        else:
            # if text in self._texts:
            #    return [(text, 0)]

            result = []
            for t in self._texts.keys():
                dist = levenshtein(text, t)  # noqa
                # if dist < 5:
                #     print(f"\t{text} == {t} {dist}")
                if dist <= dist_cutoff:
                    result.append((t, dist))
            return sorted(result, key=itemgetter(1))

    def add_text(self, text):
        assert text not in self._texts
        self._texts[text] = None
