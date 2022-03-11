import json
import pathlib

import docint
from docint.vision import Vision
from docint.doc import Doc

if __name__ == '__main__':
    viz = docint.load('reader.yml')

    doc = viz('hello3.pdf')
    doc.to_disk('docFile.json')




    
    

    
