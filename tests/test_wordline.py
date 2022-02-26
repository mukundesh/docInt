import sys

import docint
import pathlib
from docint.vision import Vision
from docint.word_line import words_in_lines
from docint.doc import Doc

if __name__ == '__main__':
    if len(sys.argv) > 1:
        doc_path = sys.argv[1]
        page_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0

        doc = Doc.from_disk(doc_path)
        word_lines = words_in_lines(doc.pages[page_idx], newline_height_multiple=1.0)

    else:
        viz = docint.load('recog.yml')
        doc = viz('hello.pdf')
        word_lines = words_in_lines(doc.pages[0])



    
