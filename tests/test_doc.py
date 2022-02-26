import docint
import pathlib
import json

from docint.vision import Vision
from docint.page import Page
from docint.doc import Doc

from docint.word import Word


@Vision.factory("hello_prabhat", default_config={"lane": 9})
class HelloLane:
    def __init__(self, lane: int):
        self.lane = lane
        print('Inside Hello Lane ')

    def __call__(self, doc):
        print(f'Inside Hello Lane: {self.lane}')
        return doc


viz = docint.load('empty.yml')
#doc = viz.build_doc('hello.pdf')
doc = viz('hello.pdf')

docFilePath = pathlib.Path('docFile.json')
json_str = doc.to_json()
docFilePath.write_text(json_str)

doc_dict = json.loads(json_str)
#Doc.update_forward_refs()
#newDoc = Doc(**doc_dict)




