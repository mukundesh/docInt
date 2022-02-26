from typing import List, Dict
import functools

from pydantic import BaseModel


class Span(BaseModel):
    start: int
    end: int

    @classmethod
    def accumulate(self, spans, ignore_chars=' '):
        def merge_spans(spans, span):
            if not spans:
                return [ span.clone() ]
            
            last_span = spans[-1]
            if last_span.overlaps_or_adjoins(span, ignore_chars):
                last_span.end = max(span.end, last_span.end)
            else:
                spans.append(span.clone())
            return spans
        
        spans.sort(key=lambda s: (s.start, len(s)))
        functools.reduce(merge_spans, spans, [])
        return spans

    @classmethod
    def reduce(self, spans, ignore_chars=' '):
        def merge_spans(spans, span):
            if not spans:
                return [ span ]
            
            last_span = spans[-1]
            if last_span.overlaps(span) or last_span.adjoins(span, ignore_chars):
                last_span.end = max(span.end, last_span.end)
            else:
                spans.append(span)
            return spans
        
        spans.sort(key=lambda s: (s.start, len(s)))
        functools.reduce(merge_spans, spans, [])
        return spans

    def clone(self):
        return Span(self.start, self.end)

    def __len__(self):
        return self.end - self.start

    def __bool__(self):
        return self.end > self.start

    def span_str(self, text):
        return f'[{self.start}:{self.end}]{text[self.slice()]}'

    def slice(self):
        return slice(self.start, self.end)


    def overlaps(self, span):
        return self.get_overlap(span) > 0

    def adjoins(self, span, text, ignore_chars=' '):
        min_end, max_start = min(span.end, self.end), max(span.start, self.start)
        overlap = max(0, min_end - max_start)
        if overlap > 0:
            return False

        gap = max_start - min_end
        gs, ge = min(max_start, min_end), max(max_start, min_end)
        gap_text = text[gs:ge].strip(ignore_chars)
        return True if gap_text == '' else False

    def overlaps_or_adjoins(self, span, ignore_chars=' '):
        min_end, max_start = min(span.end, self.end), max(span.start, self.start)
        overlap = max(0, min_end - max_start)
        if overlap > 0:
            return True

        gap = max_start - min_end
        gs, ge = min(max_start, min_end), max(max_start, min_end)
        gap_text = text[gs:ge].strip(ignore_chars)
        return True if gap_text == '' else False

    def get_overlap(self, span):
        min_end, max_start = min(span.end, self.end), max(span.start, self.start)
        return max(0,  min_end - max_start)

    def update(self, pos, offset):
        ## TODO check with pos should depend on offset sign
        if self.start >= pos:
            self.start += inc
            self.end += inc
        elif self.start < pos < self.end:
            self.end += inc

        self.start = max(self.start, 0)
        self.end = max(self.end, 0)
        
        
class SpanGroup(BaseModel):
    spans: List[Span]
    text: str

    def add(self, span):
        return self.spans.append(span)


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
    
    
    



    
