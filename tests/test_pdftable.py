import json
import pathlib

import docint
from docint.vision import Vision
from docint.doc import Doc

if __name__ == '__main__':
    viz = docint.load('pdftable.yml')
    doc  = viz('pdf_with_rects.pdf')
    doc.to_disk('pdf_with_rects.json')

    doc2 = doc.from_disk('pdf_with_rects.json')
    print(len(doc.pages))
