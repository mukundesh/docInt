import docint


def get_markers(doc):
    return [m.num_text for m in doc.pages[0].num_markers]


# TODO
# 1. page_idxs is incorrect it should be skip_page_idx
# 2. min_marker should min_marker_count
# 3. separate out the tests


def get_markers_val(doc):
    return [m.num_val for m in doc.pages[0].num_markers]


def test_simple(numbered_list_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("num_marker", pipe_config={"find_alphabet": True})
    ppln.add_pipe("list_finder", pipe_config={"find_alphabet": False, "find_roman": False})

    doc = ppln(numbered_list_path)
    assert len(doc[0].list_items) == 5

    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("num_marker")
    ppln.add_pipe("list_finder", pipe_config={"find_ordinal": False})

    doc = ppln(numbered_list_path)
    assert len(doc[0].list_items) == 3


def test_min_markers_onpage(numbered_list_path):
    ppln = docint.empty()
    ppln.add_pipe("pdf_reader")
    ppln.add_pipe("num_marker")
    ppln.add_pipe("list_finder", pipe_config={"min_markers_onpage": 15})

    doc = ppln(numbered_list_path)
    assert len(doc[0].list_items) == 0
