import docint
import pathlib
from docint.vision import Vision

if __name__ == '__main__':
    
    viz = docint.load('tablefinder.yml')
    doc = viz('hello.pdf')

    docFilePath = pathlib.Path('docFile.json')
    docFilePath.write_text(doc.to_json())




