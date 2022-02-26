import json
import pathlib

import docint
from docint.vision import Vision
from docint.doc import Doc

if __name__ == '__main__':
    viz = docint.load('recog.yml')

    print('Now process pipe_all') 
    for doc in viz.pipe_all(['hello.pdf', '1_Upload_2748.pdf']):
        doc.to_disk('docFile.json')
        
    print('Done process pipe_all')     



    
    

    
