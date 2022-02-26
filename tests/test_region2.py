import sys

import docint
import pathlib
from docint.vision import Vision
from docint.region import Region, TextConfig, Span
from docint.word_line import words_in_lines

line1 = '1348 EAT ON VANCE 7/3/95 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'
spans2 = 'idx: [0:4]=>1348< [85:90]=>1350 <'
line3 = ' EAT ON VANCE 7/3/95 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'

spans4 = '''idx: [0:4]=>1348< [85:90]=>1350 <
detail: [5:17]=>EAT ON VANCE<'''

line5 = '1348  7/3/95 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'

spans6 = '''idx: [0:4]=>1348< [85:90]=>1350 <
detail: [5:17]=>EAT ON VANCE<
numbers: [0:5]=>1348 < [17:24]=> 7/3/95<'''

line7 = ' $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'

spans8 = '''idx: [0:4]=>1348< [85:90]=>1350 <
detail: [5:17]=>EAT ON VANCE<
numbers: [0:5]=>1348 < [17:24]=> 7/3/95<
transaction: [45:53]=>3421-875<'''

word_texts1 = '1348-EAT, EAT-ON, ON-VANCE, VANCE-7/3/95, 7/3/95-$3,000.00, $3,000.00-BT, BT-TAYLOR, TAYLOR-3421-875, 3421-875-COREST, COREST-CK, CK-INVEST, INVEST-UNITED, UNITED-198374, 198374-None, 1350-CHASE, CHASE-MORTG, MORTG-7/5/95, 7/5/95-$752.45, $752.45-BT, BT-TAYLOR, TAYLOR-3421-875, 3421-875-COREST, COREST-CK, CK-JULY, JULY-CHASE, CHASE-97547231, 97547231-None'

word_texts2 = 'EAT-ON, ON-VANCE, $3,000.00-BT, BT-TAYLOR, TAYLOR-3421-875, 3421-875-COREST, COREST-CK, CK-INVEST, INVEST-UNITED, UNITED-198374, 198374-None, CHASE-MORTG, MORTG-7/5/95, 7/5/95-$752.45, $752.45-BT, BT-TAYLOR, TAYLOR-3421-875, 3421-875-COREST, COREST-CK, CK-JULY, JULY-CHASE, CHASE-97547231, 97547231-None'

word_texts3 = '1348, EAT, ON, VANCE, 7/3/95, $3,000.00, BT, TAYLOR, 3421-875, COREST, CK, INVEST, UNITED, 198374, 1350, CHASE, MORTG, 7/5/95, $752.45, BT, TAYLOR, 3421-875, COREST, CK, JULY, CHASE, 97547231'

word_texts4 = 'EAT, ON, VANCE, $3,000.00, BT, TAYLOR, 3421-875, COREST, CK, INVEST, UNITED, 198374, CHASE, MORTG, 7/5/95, $752.45, BT, TAYLOR, 3421-875, COREST, CK, JULY, CHASE, 97547231'

word_texts5 = '0-1348, 5-EAT, 9-ON, 12-VANCE, 18-7/3/95'

word_texts6 = '5-EAT, 9-ON, 12-VANCE, 25-$3,000.00, 35-BT'

line_m1 = '1348 EATON VANCE 7/3/95 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'
line_m2 = '1348 EATONVANCE 7/3/95 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'
line_m3 = '1348EATONVANCE 7/3/95 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'
line_m4 = '1348EATONVANCE 7/3/95 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE97547231'

line_R1 = '1348EATONVANCE 7/3/96 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE97547231'

line_R2 = '1348EATONVANCE 7/3/1996 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE97547231'

line_R3 = '1348EATONVANCE 7/3 $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE97547231'

line_R4 = '1348EATONVANCE $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE97547231'

line_R5 = '1348EATONVANCE $3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE97547231'

line_R6= '$3,000.00 BT TAYLOR 3421-875 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE97547231'


line_B1 = '1348 EAT ON VANCE 7/3/95 $3,000.00 BT TAYLOR 3421 COREST CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'

line_B2 = '1348 EAT ON VANCE 7/3/95 $3,000.00 BT TAYLOR 3421 CK INVEST UNITED 198374 1350 CHASE MORTG 7/5/95 $752.45 BT TAYLOR 3421-875 COREST CK JULY CHASE 97547231'

line_B3 = '1348 EAT ON VANCE 7/3/95 $3,000.00 BT TAYLOR 3421875 COREST CK JULY CHASE 97547231'

word_texts_B1 = '1348, EAT, ON, VANCE, 7/3/95, $3,000.00, BT, TAYLOR, 3421, COREST, CK, INVEST, UNITED, 198374, 1350, CHASE, MORTG, 7/5/95, $752.45, BT, TAYLOR, 3421-875, COREST, CK, JULY, CHASE, 97547231'

word_texts_B2 = '1348, EAT, ON, VANCE, 7/3/95, $3,000.00, BT, TAYLOR, 3421, CK, INVEST, UNITED, 198374, 1350, CHASE, MORTG, 7/5/95, $752.45, BT, TAYLOR, 3421-875, COREST, CK, JULY, CHASE, 97547231'

word_texts_B3 = '1348, EAT, ON, VANCE, 7/3/95, $3,000.00, BT, TAYLOR, 3421, 875, COREST, CK, JULY, CHASE, 97547231'





if __name__ == "__main__":
    viz = docint.load("html.yml")
    doc = viz("sample2.pdf")

    region = Region(words=doc.pages[0].words[90:117])
    region.word_lines = words_in_lines(region, para_indent=False)

    print("\n=>1. Starting line")
    for line_idx, word_line in enumerate(region.word_lines):
        print(f"[{line_idx}]", end=":")
        print(" ".join(w.text for w in word_line))
    print(region.line_text())
    assert region.line_text() == line1

    print("\n=>2. Adding two idx spans")
    region.add_span(0, 4, "idx")
    region.add_span(85, 90, "idx")  # extra space is on purpose
    print(region.str_spans())
    assert region.str_spans() == spans2

    print("\n=>3. Printing removing idx spans")
    rm_idx_config = TextConfig(rm_labels=["idx"])
    print(region.line_text(rm_idx_config))
    assert region.line_text(rm_idx_config) == line3

    print("\n=>4. Adding detail span on removed idx spans")
    region.add_span(1, 13, "detail", rm_idx_config)
    print(region.str_spans())
    assert region.str_spans() == spans4

    print("\n=>5. Printing removing detail spans")
    rm_detail_config = TextConfig(rm_labels=["detail"])
    print(region.line_text(rm_detail_config))
    assert region.line_text(rm_detail_config) == line5

    print("\n=>6. Adding overlapping number span on removed detail span")
    region.add_span(0, 12, "numbers", rm_detail_config)
    print(region.str_spans())    
    assert region.str_spans() == spans6

    print("\n=>7. printing removing detail, number, idx spans")
    rm_all_config = TextConfig(rm_labels=["idx", "numbers", "detail"])
    print(region.line_text(rm_all_config))    
    assert region.line_text(rm_all_config) == line7
    
    print("\n=>8. Adding outside transaction span on removed detail, number, idx span")
    region.add_span(21, 29, "transaction", rm_all_config)
    print(region.str_spans())    
    assert region.str_spans() == spans8

    print("\n=>I1. printing all words in pairs")
    word_texts = []
    for word, next_word in region.iter_word_pairs():
        word_texts.append(f'{word.text}-{next_word.text if next_word else "None"}')
    print(region.str_spans())
    print(region.line_text())

    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == word_texts1
    

    print("\n=>I2. printing all words in pairs on removed number, idx span")
    rm_idx_number_config = TextConfig(rm_labels=["idx", "numbers"])
    word_texts = []
    for word, next_word in region.iter_word_pairs(rm_idx_number_config):
        word_texts.append(f'{word.text}-{next_word.text if next_word else "None"}')
        
    print(region.str_spans())
    print(region.line_text(rm_idx_number_config))

    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == word_texts2


    print("\n=>I3. printing all words")
    word_texts = []
    for idx, word in region.iter_words():
        word_texts.append(f'{word.text}')        
    print(region.str_spans())
    print(region.line_text())
    
    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == word_texts3

    print("\n=>I4. printing all words on removed number, idx span")
    rm_idx_number_config = TextConfig(rm_labels=["idx", "numbers"])
    word_texts = []
    for idx, word in region.iter_words(rm_idx_number_config):
        word_texts.append(f'{word.text}')
        
    print(region.str_spans())
    print(region.line_text(rm_idx_number_config))
    
    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == word_texts4


    print("\n=>I5. printing all words without config")
    rm_idx_number_config = TextConfig(rm_labels=["idx", "numbers"])
    word_texts = [ f'{pos}-{w.text}' for (pos, w) in region.iter_words_startpos() ]
    words_texts_str = ", ".join(word_texts[:5])    
    print(words_texts_str)
    assert words_texts_str == word_texts5


    print("\n=>I6. printing all words without config")
    rm_idx_number_config = TextConfig(rm_labels=["idx", "numbers"])
    word_texts = [ f'{pos}-{w.text}' for (pos, w) in region.iter_words_startpos(rm_idx_number_config) ]
    words_texts_str = ", ".join(word_texts[:5])    
    print(words_texts_str)
    assert words_texts_str == word_texts6

    print("\n=>W1. printing all span_words")
    span = Span(start=0, end=15, label='no_label')
    word_texts = [w.text for w in region.get_span_words(span)]
    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == '1348, EAT, ON, VANCE'

    print("\n=>C1. Printing color text. ")
    color_dict = {
        'idx': 'white on red',
        'detail': 'white on green',
        'numbers': 'white on magenta',
        'transaction': 'white on black',
    }
    region.print_color('Error', color_dict)

    print("\n=>B1. Add span left middle, right end")
    region.add_span(49, 53, 'boundary')
    rm_boundary_config = TextConfig(rm_labels=['boundary'])
    print(region.line_text(rm_boundary_config))
    assert region.line_text(rm_boundary_config) == line_B1
    
    word_texts = []
    for text, word in region.iter_word_text(rm_boundary_config):
        word_texts.append(f'{text}')
    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == word_texts_B1
        
    print("\n=>B2. Add span left middle, right end next word")
    region.add_span(49, 60, 'boundary')
    rm_boundary_config = TextConfig(rm_labels=['boundary'])
    print(region.line_text(rm_boundary_config))
    assert region.line_text(rm_boundary_config) == line_B2
    
    word_texts = []
    for text, word in region.iter_word_text(rm_boundary_config):
        word_texts.append(f'{text}')
    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == word_texts_B2    

    print("\n=>B3. Add span left middle, right end far next middle")
    region.add_span(49, 132, 'boundary')
    rm_boundary_config = TextConfig(rm_labels=['boundary'])
    print(region.line_text(rm_boundary_config))
    assert region.line_text(rm_boundary_config) == line_B3
    
    word_texts = []
    for text, word in region.iter_word_text(rm_boundary_config):
        word_texts.append(f'{text}')
    words_texts_str = ", ".join(word_texts)
    print(words_texts_str)
    assert words_texts_str == word_texts_B3
    
    detail1, detail2, detail3 = region.words[1], region.words[2], region.words[3]    
    print("\n=>M1. Merge detail1 and detail2")
    region.merge_word(detail1, detail2)
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_m1
    
    print("\n=>M2. Merge detail2 and detail3")
    region.merge_word(detail1, detail3)
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_m2    

    print("\n=>M3. Merge first word")
    region.merge_word(region.words[0], region.words[1])    
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_m3    


    print("\n=>M4. Merge last two words")
    region.merge_word(region.words[-2], region.words[-1])    
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_m4    


    date_word = region.words[4]
    print("\n=>R1. Replace date with same len")
    region.replace_word_text(date_word, '7/3/95', '7/3/96')
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_R1

    print("\n=>R2. Replace date with longer len")
    region.replace_word_text(date_word, '7/3/96', '7/3/1996')
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_R2

    print("\n=>R3. Replace date with shorter len")
    region.replace_word_text(date_word, '7/3/1996', '7/3')
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_R3    

    print("\n=>R4. Replace date with empty")
    region.replace_word_text(date_word, '<all>', '')
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_R4    

    print("\n=>R5. Replace last word with empty")
    region.replace_word_text(region.words[-1], '<all>', '')
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_R5    

    print("\n=>R6. Replace first word with empty")
    region.replace_word_text(region.words[0], '<all>', '')
    print(region.str_spans())
    print(region.line_text())
    assert region.line_text() == line_R6    

    # TODO how to handle space around the span ?
