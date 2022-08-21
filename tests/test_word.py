def test_properties(two_lines_doc):
    doc = two_lines_doc

    assert doc[0][0].text == "A"
    assert doc[0][1].text == "quick"

    assert doc.pages[0].words[1].text == "quick"
    assert doc.pages[0].words[0].page_idx == 0

    assert doc[0][0].path == "page[0].words[0]"
    assert doc[0][0].path_abbr == "pa0.wo0"


def test_dunder(two_lines_doc):
    doc = two_lines_doc
    assert len(doc[0][0]) == 1

    assert doc[0][0]

    doc.edit(["clearWord pa0.wo0"])
    assert not doc[0][0]

    assert doc[0][0].orig_text == "A"
