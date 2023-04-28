from ..vision import Vision


@Vision.factory(
    "ascii_converter",
)
class AsciiConverter:
    def __init__(self):
        pass

    def convert_text(self, text):
        from text_unidecode import unidecode

        new_text = unidecode(text)
        return new_text, None

    def __call__(self, doc):
        edits = []
        for (page, word) in [(p, w) for p in doc.pages for w in p.words]:
            if not word.text.isascii():
                path = f"pa{page.page_idx}.wo{word.word_idx}"
                new_text, err = self.convert_text(word.text)
                if err:
                    print(f"Path: {path} Failed: {err.msg}")
                else:
                    new_text = new_text.replace("'", "")
                    print(f"Replacing {word.text} -> {new_text}")
                    edits.append(f"replaceStr {path} <all> '{new_text}'")
        print("\n".join(edits))
        print(f"Replaced text in {len(edits)} words")
        doc.edit(edits)
        return doc
