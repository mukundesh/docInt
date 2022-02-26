import docint
import pathlib
from docint.vision import Vision
from docint.doc import Doc

if __name__ == '__main__':
    
    viz = docint.load('listfinder.yml')
    doc = viz('hello.pdf')

    docFilePath = pathlib.Path('docFile.json')
    docFilePath.write_text(doc.to_json())

    
    newDoc = Doc.from_disk('docFile.json')
    newDoc.to_disk('docFile2.json')



