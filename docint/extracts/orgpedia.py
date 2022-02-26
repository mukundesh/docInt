from typing import List
from ..region import Region, Span

class Officer(Region):
    salut: str
    name: str
    full_name: str
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

    spans: List[Span]

    @property
    def dept(self):
        return self.dept_hpath[-1]

    @property
    def role(self):
        return self.role_hpath[-1]

    @classmethod
    def build(cls, words, post_str, dept, role, juri=None, loca=None, stat=None):
        def build_spans(label, spans):
            return [Span(start=s, end=e, label=label) for (s,e) in spans]
        
        dept_spans = build_spans('dept', dept.spans) if dept else []
        role_spans = build_spans('role', role.spans) if role else []
        juri_spans = build_spans('juri', juri.spans) if juri else []
        loca_spans = build_spans('loca', loca.spans) if loca else []
        stat_spans = build_spans('stat', stat.spans) if stat else []

        dept_hpath = dept.get_hpath() if dept else []
        role_hpath = role.get_hpath() if role else []
        juri_hpath = juri.get_hpath() if juri else []
        loca_hpath = loca.get_hpath() if loca else []
        stat_hpath = stat.get_hpath() if stat else []                                
        
        spans = dept_spans + role_spans + juri_spans + loca_spans + stat_spans

        return Post(words=words, word_line=[words], post_str=post_str,
                    dept_hpath=dept_hpath, role_hpath=role_hpath,
                    juri_hpath=juri_hpath, loca_hpath=loca_hpath,
                    stat_hpath=stat_hpath, spans=spans)
    
        
class OrderDetail(Region):
    officer: Officer
    continues: List[Post] = []
    relinquishes: List[Post] = []            
    assumes: List[Post] = []
    detail_idx: int
    is_valid: bool = True
    #extra_spans: [Span] = []

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
