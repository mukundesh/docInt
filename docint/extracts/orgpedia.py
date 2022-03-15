import datetime

from typing import List
from ..region import Region, Span

class Officer(Region):
    salut: str
    name: str
    full_name: str
    birth_date: datetime.date = None
    relative_name: str = ''
    home_district: str = ''
    posting_date: datetime.date = None
    cadre: str = ''
    
    officer_idx: int = -1
    officer_ID: str = ''
    lang: str = 'en'

    @classmethod
    def build(cls, words, salut, name):
        full_name = salut + ' ' + name
        return Officer(words=words, word_line=[words], salut=salut, name=name,
                       full_name=full_name)


class Post(Region):
    post_str: str

    dept_hpath: List[str]
    role_hpath: List[str]
    juri_hpath: List[str]
    loca_hpath: List[str]
    stat_hpath: List[str]

    dept_spans: List[Span]
    role_spans: List[Span]
    juri_spans: List[Span]
    loca_spans: List[Span]
    stat_spans: List[Span]            

    @property
    def dept(self):
        return self.dept_hpath[-1]

    @property
    def role(self):
        return self.role_hpath[-1]

    @property
    def spans(self):
        return self.dept_spans + self.role_spans + self.juri_spans + self.loca_spans + self.stat_spans

    @property
    def spans_dict(self):
        s_dict = {'dept': self.dept_spans, 'role': self.role_spans, 'juri': self.juri_spans,
                     'loca': self.loca_spans, 'stat': self.stat_spans}
        return dict((field, spans) for field, spans in s_dict.items() if spans)


    @classmethod
    def to_str(self, posts, post_str):
        p = post_str
        posts_to_strs = []
        for post in posts:
            strs = [ f'{f[0].upper()}:{Span.to_str(p, s)}<' for (f, s) in post.spans_dict.items() ]
            posts_to_strs.append(' '.join(strs))
        return '-'.join(posts_to_strs)

    @classmethod
    def build(cls, words, post_str, dept=None, role=None, juri=None, loca=None, stat=None):
        def build_spans(label, spans):
            return [Span(start=span.start, end=span.end, label=label) for span in spans]
        
        dept_spans = build_spans('dept', dept.spans) if dept else []
        role_spans = build_spans('role', role.spans) if role else []
        juri_spans = build_spans('juri', juri.spans) if juri else []
        loca_spans = build_spans('loca', loca.spans) if loca else []
        stat_spans = build_spans('stat', stat.spans) if stat else []

        dept_hpath = dept.hierarchy_path if dept else []
        role_hpath = role.hierarchy_path if role else []
        juri_hpath = juri.hierarchy_path if juri else []
        loca_hpath = loca.hierarchy_path if loca else []
        stat_hpath = stat.hierarchy_path if stat else [] 
        
        return Post(words=words, word_line=[words], post_str=post_str,
                    dept_hpath=dept_hpath, role_hpath=role_hpath,
                    juri_hpath=juri_hpath, loca_hpath=loca_hpath,
                    stat_hpath=stat_hpath, dept_spans=dept_spans,
                    role_spans=role_spans, juri_spans=juri_spans,
                    loca_spans=loca_spans, stat_spans=stat_spans)
                    
    
        
class OrderDetail(Region):
    officer: Officer
    continues: List[Post] = []
    relinquishes: List[Post] = []            
    assumes: List[Post] = []
    detail_idx: int
    is_valid: bool = True

    @property
    def page_idx(self):
        return self.words[0].page_idx

    @classmethod
    def build(cls, words, officer, post_info, detail_idx):
        return OrderDetail(words=words, word_line=[words], officer=officer,
                           continues=post_info.continues,
                           relinquishes=post_info.relinquishes,
                           assumes=post_info.assumes,
                           detail_idx=detail_idx)
