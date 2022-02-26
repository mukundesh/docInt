import docint
import pathlib
from docint.vision import Vision
from docint.region import Region, TextConfig
from docint.word_line import words_in_lines

if __name__ == '__main__':
    viz = docint.load('html.yml')
    doc = viz('sample.pdf')

    #sys.exit(1)

    region = Region(words=doc.pages[0].words[142:166])
    region.word_lines = words_in_lines(region, para_indent=False)

    for line_idx, word_line in enumerate(region.word_lines):
        print(f'[{line_idx}]', end=':')
        print(' '.join(w.text for w in word_line))


    # overlapping spans followed by line_text
    print(region.line_text())

    
    region.add_span(2, 7, 'person')
    region.add_span(10, 15, 'person')
    region.add_span(2, 25, 'person')
    region.add_span(10, 25, 'person')    

    rm_person_config = TextConfig(rm_labels=['person'])
    print(region.line_text(rm_person_config))    
    

    # Now merge words 1, 2 and 3
    print(region.line_text())
    print('Before ---------------------')
    print(region.str_spans())
    print('-----------------------')    
    
    region.merge_word(region.words[1], region.words[2])

    print(region.line_text())    
    print('After --------------------')
    print(region.str_spans())
    print('-----------------------')

    region.merge_word(region.words[1], region.words[3])

    print(region.line_text())    
    print('After --------------------')
    print(region.str_spans())
    print('-----------------------')

    print(region.line_text(rm_person_config))        


    #region.add_span(29, 43, 'ignore', rm_person_config)
    
    
