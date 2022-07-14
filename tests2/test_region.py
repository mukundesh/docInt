def test_properties(two_lines_doc):
    doc = two_lines_doc
    region = doc[0][:3]
    assert len(region) == 3
    assert region

    assert region.page_idx == 0
    assert len(region.get_regions()) == 1
