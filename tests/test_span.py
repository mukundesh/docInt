from docint.span import Span

t1 = 'The quick brown fox jumps over the lazy dog'

if __name__ == '__main__':
    
    # test subsumed
    s1 = Span(start=4, end=9) # quick
    s2 = Span(start=5, end=8) # 
    s3 = Span(start=4, end=7)
    s4 = Span(start=6, end=9)     


    slong = Span(start=0, end=15) # A quick brown

    assert s1.subsumes(s1) and s1.subsumes(s2) and s1.subsumes(s3) and s1.subsumes(s4)

    assert (not s1.subsumes(slong)) and (not s2.subsumes(s1)) and (not s3.subsumes(s1))


    print(Span.remove_subsumed([s1, s2, s3, s4]))
    print(Span.remove_subsumed([s4, s3, s2, s1]))
    print(Span.remove_subsumed([s4, s3, s2]))
    print(Span.remove_subsumed([s1, s2, s3, s4, slong]))    

    
    
