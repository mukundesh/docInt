import docint
from docint.vision import Vision

@Vision.factory("hello_prabhat", default_config={"lane": 9})
class HelloLane:
    def __init__(self, lane: int):
        self.lane = lane
        print('Inside Hello Lane ')

    def __call__(self, doc):
        print(f'Inside Hello Lane: {self.lane}')
        return doc


viz = docint.load('empty.yml')
doc = viz.build_doc('hello.pdf')



