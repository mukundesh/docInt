from typing import Dict, List

from pydantic import BaseModel

from .span import Span


class TextPara(BaseModel):
    t: str
    label_spans: Dict[str, List[Span]] = {}

    @classmethod
    def from_text(cls, text):
        return TextPara(t=text)

    @property
    def text(self):
        return self.t

    def add_label(self, spans, label):
        spans = spans if isinstance(spans, list) else [spans]
        self.label_spans.setdefault(label, []).extend(spans)

    def get_spans(self, label):
        return self.label_spans.get(label, [])

    def get_texts(self, label):
        return [s.span_str(self.text) for s in self.get_spans(label)]

    def get_labels(self, span):
        labels = []
        for label, spans in self.label_spans.items():
            matching_spans = [s for s in spans if s.subsumes(span)]
            if matching_spans:
                labels.append(label)
        return labels

    def clear_labels(self):
        self.label_spans.clear()

    def get_texts_labels(self, only_single_label):
        assert self.text[0] != " "
        span_start = 0
        texts, labels = [], []

        for text in self.text.split():
            span = Span(start=span_start, end=span_start + len(text))

            span_labels = self.get_labels(span)
            assert len(span_labels) <= 1, "Number of span labels is > 1 {span_labels}"

            if span_labels:
                labels.append(span_labels[0])
            else:
                labels.append(None)
            texts.append(text)

            span_start += len(text) + 1

        return texts, labels
