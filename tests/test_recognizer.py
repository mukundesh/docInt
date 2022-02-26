import json
import pathlib

import docint
from docint.vision import Vision
from docint.doc import Doc

if __name__ == '__main__':
    viz = docint.load('recog.yml')

    doc = viz('hello.pdf')
    doc.to_disk('docFile.json')

    
    newDoc = Doc.from_disk('docFile.json')
    newDoc.to_disk('docFile2.json')




    
    

    
