import docint
import pathlib
from docint.vision import Vision
from docint.doc import Doc

if __name__ == '__main__':
    
    viz = docint.load('listfinder.yml')
    doc = viz('hello.pdf')

    doc.to_disk('docFile_lister.json')




