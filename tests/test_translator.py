import docint


def test_doc_translator(table_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("num_marker")
    ppln.add_pipe("list_finder")
    ppln.add_pipe("table_finder")
    ppln.add_pipe("doc_translator_hf")

    doc = ppln(table_path)

    first_table = doc.pages[0].table_trans[0]

    # Note headers are not found by the table_finder as it goes by numbers
    # 2.5 A.U gets translated as 2.5  ए. यू. by the translator
    assert first_table[0][0] == "१"
    assert first_table[2][1] == "पृथ्वी"
    assert first_table[3][2] == "2. 5 ए. यू."

    # print(doc.pages[0].table_trans)
    # [[['१', 'पारा', '0. 4 ए. यू.'], ['२', 'शुक्र', '0. 0. 0 ए. यू.'], ['३', 'पृथ्वी', '1. 1 ए. यू.'], ['४', 'मंगल ग्रह', '2. 5 ए. यू.'], ['५', 'बृहस्पति', '80. 2. 2 ए. यू.'], ['६', 'शनि', '83 9.6 ए. यू.'], ['७', 'यूरेनस', '27 19.2 ए. यू.'], ['८', 'नेपच्यून', '14 30.0 ए. यू.'], ['९', 'प्लूटो', '0 39.5 ए. यू.']]]
