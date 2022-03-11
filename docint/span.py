from typing import List, Dict
import functools
import operator as op

from pydantic import BaseModel


class Span(BaseModel):
    start: int
    end: int

    # TODO should this be span_group ? or just spans
    @classmethod
    def blank_text(cls, spans, text):
        spans.sort(key=op.attrgetter('start'))
        assert cls.is_non_overlapping(spans)
        span_texts, pre_span_start = [], 0
        for span in spans:
            span_texts.append(text[pre_span_start:span.start])
            span_texts.append(' ' * len(span))
            pre_span_start = span.end
        return ''.join(span_texts)

    @classmethod
    def unmatched_texts(cls, spans, text):
        spans.sort(key=op.attrgetter('start'))
        assert cls.is_non_overlapping(spans)
        
        unmatched_texts, pre_span_start = [], 0
        for span in spans:
            u_text = text[pre_span_start:span.start]
            if u_text:
                unmatched_texts.append(u_text)
            pre_span_start = span.end
        return unmatched_texts

    @classmethod
    def is_non_overlapping(cls, spans):
        if len(spans) < 2:
            return True
        
        for span1, span2 in zip(spans[:-1], spans[1:]):
            if span1.end > span2.start:
                return False
        return True

    
    @classmethod
    def str_spans(cls, spans):
        return ', '.join(str(s) for s in spans) 


    @classmethod
    def accumulate(cls, spans, text=None, ignore_chars=' '):
        def merge_spans(spans, span):
            if not spans:
                return [ span.clone() ]
            
            last_span = spans[-1]
            if last_span.overlaps_or_adjoins(span, text, ignore_chars):
                last_span.end = max(span.end, last_span.end)
            else:
                spans.append(span.clone())
            return spans

        #print(cls.str_spans(spans))

        spans.sort(key=lambda s: (s.start, len(s)))
        new_spans = functools.reduce(merge_spans, spans, [])
        return new_spans

    def clone(self):
        return Span(start=self.start, end=self.end)

    def __len__(self):
        return self.end - self.start

    def __bool__(self):
        return self.end > self.start

    def __lt__(self, other):
        return (self.start, self.end) < (other.start, other.end)


    def __contains__(self, pos):
        #print(f'\t\t{pos} in {self.start}:{self.end}', end=" result> ")
        if isinstance(pos, int):
            res = self.start <= pos < self.end
        return res

    def __str__(self):
        return f'[{self.start}:{self.end}]'
    

    def span_str(self, text):
        #return f'[{self.start}:{self.end}]{text[self.slice()]}'
        return text[self.slice()]    

    def slice(self):
        return slice(self.start, self.end)


    def overlaps(self, span):
        return self.get_overlap_len(span) > 0

    def overlaps_any(self, spans):
        return any(span for span in spans if self.overlaps(span))

    def adjoins(self, span, text=None, ignore_chars=' '):
        min_end, max_start = min(span.end, self.end), max(span.start, self.start)
        overlap = max(0, min_end - max_start)
        if overlap > 0:
            return False

        gap = max_start - min_end
        if text is None:
            return True if gap == 0 else False
        else:
            gs, ge = min(max_start, min_end), max(max_start, min_end)
            gap_text = text[gs:ge].strip(ignore_chars)
            return True if gap_text == '' else False

    def overlaps_or_adjoins(self, span, text=None, ignore_chars=' '):
        min_end, max_start = min(span.end, self.end), max(span.start, self.start)
        overlap = max(0, min_end - max_start)
        if overlap > 0:
            return True

        gap = max_start - min_end
        if text is None:
            return True if gap == 0 else False
        else:
            gs, ge = min(max_start, min_end), max(max_start, min_end)
            gap_text = text[gs:ge].strip(ignore_chars)
            return True if gap_text == '' else False

    def get_overlap_len(self, span):
        min_end, max_start = min(span.end, self.end), max(span.start, self.start)
        return max(0,  min_end - max_start)

    def update(self, pos, inc):
        ## TODO check with pos should depend on offset sign
        if self.start >= pos:
            self.start += inc
            self.end += inc
        elif self.start < pos < self.end:
            self.end += inc

        self.start = max(self.start, 0)
        self.end = max(self.end, 0)

    @classmethod
    def to_str(self, span_str, spans):
        return ','.join([span_str[s.slice()] for s in spans])
    
        
        
class SpanGroup(BaseModel):
    spans: List[Span]
    text: str

    def add(self, span):
        return self.spans.append(span)

    def __iter__(self):
        for span in self.spans:
            yield span


    @property
    def min_start(self):
        return min([s.start for s in self.spans])

    @property
    def max_end(self):
        return max([s.end for s in self.spans])

    @property
    def full_span(self):
        return Span(start=self.min_start, end=self.max_end)

    @property
    def span_len(self):
        return self.max_end - self.min_start


    def overlaps(self, span_group):
        return self.full_span.overlaps(span_group.full_span)


    def overlap_type(self, word_span):
        overlap_spans = [ s for s in self.spans if word_span.overlaps(s) ]
        if not overlap_spans:
            return 'none', None

        assert len(overlap_spans) == 1
        overlap_len = word_span.get_overlap_len(overlap_spans[0])
            
        if overlap_len == len(word_span):
            return 'full', word_span
        else:
            o_span = overlap_spans[0]
            if word_span.start < o_span.start < word_span.end:
                return 'partial', Span(start=o_span.start, end=word_span.end)
            else:
                return 'partial', Span(start=word_span.start, end=o_span.end)
    



    
