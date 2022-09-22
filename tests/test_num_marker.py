import docint


def get_markers(doc):
    return [m.num_text for m in doc.pages[0].num_markers]


# TODO
# 1. page_idxs is incorrect it should be skip_page_idx
# 2. min_marker should min_marker_count


def get_markers_val(doc):
    return [m.num_val for m in doc.pages[0].num_markers]


def test_num_markers(numbered_list_doc):
    # json_str = numbered_list_doc.to_json()

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['1', '2', 'i', 'ii', 'iii', '3', '4', '5']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'include_zero': True})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['0', '1', '2', 'i', 'ii', 'iii', '3', '4', '5']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'find_roman': False})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['1', '2', '3', '4', '5']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'find_ordinal': False})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['i', 'ii', 'iii']
    assert get_markers_val(doc) == [1, 2, 3]

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'find_ordinal': False})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['i', 'ii', 'iii']
    assert get_markers_val(doc) == [1, 2, 3]

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'find_ordinal': False, 'find_roman': False})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == []

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'find_ordinal': False, 'find_roman': False, 'find_alphabet': True})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['a', 'b', 'c', 'a', 'b', 'c']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'min_marker': 8})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['1', '2', 'i', 'ii', 'iii', '3', '4', '5']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'min_marker': 9})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == []

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'num_chars': ''})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == []

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'find_alphabet': True, 'num_chars': ')'})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['a', 'b', 'c']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'max_number': 2})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['1', '2', 'i', 'ii']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'x_range': (0, 0.18)})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['1', '2', '3', '4', '5']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'x_range': (0.18, 0.25)})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['i', 'ii', 'iii']

    ppl = docint.empty()
    ppl.add_pipe('pdf_reader')
    ppl.add_pipe('num_marker', pipe_config={'y_range': (0.25, 1.0)})
    doc = ppl('tests/numbered_list.pdf')
    assert get_markers(doc) == ['3', '4', '5']
