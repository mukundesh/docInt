import docint
import pathlib
from docint.vision import Vision

if __name__ == '__main__':
    
    viz = docint.load('2748.yml')
    doc = viz('1_Upload_2748.pdf')

    docFilePath = pathlib.Path('docFile.json')
    docFilePath.write_text(doc.to_json())




