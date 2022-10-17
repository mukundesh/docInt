from ..vision import Vision


@Vision.factory(
    "height_calc",
    default_config={"conf_dir": "conf", "dependencies": ["numpy"]},
)
class HeightCalculator:
    def __init__(self, conf_dir, dependencies):
        self.conf_dir = conf_dir
        self.dependencies = dependencies

    def __call__(self, doc):
        print("INSIDE HEIGHTCALC")
        # import numpy as np
        doc.add_extra_page_field("avg_word_height", ("noparse", "", ""))
        for page in doc.pages:
            page.avg_word_height = 1.0
            # page.avg_word_height = np.average(w.height for w in page.words)
        return doc
