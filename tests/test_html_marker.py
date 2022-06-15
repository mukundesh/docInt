import docint
import pathlib
from docint.vision import Vision


if __name__ == '__main__':
    viz = docint.load('html_only.yml')
    doc = viz('docFile_marker.json')
    



