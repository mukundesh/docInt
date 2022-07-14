def test_properties(two_pages_doc):
    page0 = two_pages_doc[0]

    assert page0.width == 595
    assert page0.height == 842
    assert page0.size == (595, 842)

    assert len(two_pages_doc.pages) == 2


def test_getitem(two_pages_doc):
    page1 = two_pages_doc[1]

    assert page1[0].text == "A"
    assert len(page1[:3]) == 3
    assert len(page1[:3].words) == 3


def test_xyrange(two_pages_doc):
    page1 = two_pages_doc[1]

    lt_region = page1.words_to("left", page1[0])
    assert len(lt_region) == 0

    rt_region = page1.words_to("right", page1[0])
    assert len(rt_region) == 8

    page0 = two_pages_doc[0]
    top_region = page0.words_to("above", page0[9])  # second line
    assert len(top_region) == 1

    bot_region = page0.words_to("below", page0[0])  # second line
    assert len(bot_region) == 1

    top_top_region = page0.words_to("above", page0[0])  # second line
    assert len(top_top_region) == 0
