from docint.span import Span

# Texts    : The quick brown fox jumped over the lazy fox.
# pos_idxs : 0   4     10    16  20     27   32  36   41


def S(s, e):
    return Span(start=s, end=e)


def test_properties():
    s1 = S(3, 9)

    assert len(s1) == 6
    assert 3 in s1 and 5 in s1 and 8 in s1
    assert 9 not in s1
    assert s1

    s2 = S(4, 8)
    assert s1 < s2
    assert str(s1) == "[3:9]"
    assert s1.overlaps(s2) and s2.overlaps(s1)
    assert s1.get_overlap_len(s2) == s2.get_overlap_len(s1) == 4

    s3 = S(1, 3)
    assert not s1.overlaps(s3)

    spans = [S(3, 5), S(5, 7), S(7, 9)]

    assert s1.overlaps_all(spans)
    assert s2.overlaps_all(spans)
    assert s3.adjoins(s1) and s1.adjoins(s3)

    s4 = S(1, 2)

    assert not s4.overlaps_or_adjoins(s1) and not s1.overlaps_or_adjoins(s4)

    assert s1.subsumes(s2) and not s2.subsumes(s1)

    s5 = S(4, 3)

    assert not s5

    s6 = s4.clone()
    assert id(s6) != id(s4) and isinstance(s6, Span)


def test_multi_span():
    text = "The quick brown fox jumped over the lazy fox."

    s1 = S(0, 3)
    s2 = S(4, 9)
    s3 = S(10, 15)

    spans = Span.accumulate([])
    assert len(spans) == 0

    spans = Span.accumulate([s1])
    assert len(spans) == 1

    spans = Span.accumulate([s1, s2, s3])
    assert len(spans) == 3

    spans = Span.accumulate([s1, s2, s3], text=text, ignore_chars="")
    assert len(spans) == 3

    spans = Span.accumulate([s1, s2, s3], text=text, ignore_chars=" ")
    assert len(spans) == 1 and spans[0].start == 0 and spans[0].end == 15

    assert Span.is_non_overlapping([s1, s2, s3])

    assert Span.is_non_overlapping([s1, s2, s3] + [S(3, 4), S(9, 10)])
    assert not Span.is_non_overlapping([s1, s2, s3] + [S(2, 4), S(9, 10)])

    spans = Span.remove_subsumed([s1, s2, s3, S(0, 2), S(2, 4)])
    assert len(spans) == 4

    spans = Span.remove_subsumed([s1, s2, s3, S(0, 9), S(2, 4)])
    assert len(spans) == 2

    spans = Span.remove_subsumed([s1, s2, s3, S(0, 15), S(2, 4)])
    assert len(spans) == 1

    long_span = S(0, 45)

    spans = long_span.get_non_overlapping([s1])
    assert len(spans) == 1 and spans[0].start == 3 and spans[0].end == 45

    spans = long_span.get_non_overlapping([s2])
    assert len(spans) == 2 and spans[0].start == 0 and spans[0].end == 4

    assert s1.get_non_overlapping([s2]) == [s1]
    assert s1.get_non_overlapping([S(2, 5)]) == [S(0, 2)]
