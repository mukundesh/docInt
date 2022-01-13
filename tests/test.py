import docint
from docint.vision import Vision



# @Vision.component("hello_word",
#                   requires=["page._.list_texts"],
#                   assigns=["page._.list_annots"],
#                   )

# def annotateListText(doc):
#     print("Hello World")
#     return doc






@Vision.factory("hello_world", default_config={'country': 'india'})
def create_hw(country:str):
    def my_hw(doc):
        # Do something to the doc
        print(f'Processing the DOC country: {country}')
        return doc
    return my_hw

@Vision.factory("hello_india", default_config={"state": 'mp'})
def create_hello_india(state: str):
    return HelloIndia(state)

class HelloIndia:
    def __init__(self, state: str):
        self.state = state
        print('INside INIT')

    def __call__(self, doc):
        print(f'Inside call: {self.state}')
        return doc

@Vision.factory("hello_prabhat", default_config={"lane": 9})
class HelloLane:
    def __init__(self, lane: int):
        self.lane = lane
        print('Inside Hello Lane ')

    def __call__(self, doc):
        print(f'Inside Hello Lane: {self.lane}')
        return doc



@Vision.component("hello_pune")
def component_hellow(doc):
    print('Inside hello_pune')
    return doc

if __name__ == '__main__':
    viz = docint.load('empty.yml')
    viz.add_pipe('hello_pune', name='hello_pune2')

    viz.add_pipe('hello_india', name='hello_india2',
                 pipe_config={'state': 'goa'})    

    
    print('DONE CREATING VIZ')
    #doc = viz('hello.pdf')

    docs = viz.pipe(['hello.pdf', 'hello2.pdf'])
    for doc in docs:
        print(doc)
