"""
Glossary:
1. Hiearchy
2. HiearchyNode
3. MatchedPath
4. Level

Additional tags:

1. direct: No requirement of parent tag to be present - Global option
2. crossHier:

Additional matching:
1. non-overlapping vs overlapping



"""
from dataclasses import dataclass
from pathlib import Path
from itertools import chain, groupby
import itertools as it
import logging
from operator import attrgetter
from more_itertools import first, last



from docint.span import Span, SpanGroup
from docint.util import is_readable, read_config_from_disk

lgr = logging.getLogger(__name__)

@dataclass
class MatchOptions:
    ignore_case: bool = True
    longest_name_first: bool = True
    match_on_word_boundary: bool = False
    word_boundary_chars: str = ' .-()/,:&‐'
    merge_strategy: str = 'adjoin' # child_span
    select_strategy: str = 'non_overlapping' # at_start, sum_span_len, first, 
    select_level: str = ''


class HierarchyNode:
    def __init__(self, name, alias, hierarchy_path, level, children, node_info):
        self.name = name
        self.alias = alias
        self.hierarchy_path = tuple(hierarchy_path)
        self.level = level
        self.children = children

        self.node_info = node_info

        self.parent = None
        self.u_parent = None

        for child in self.children:
            child.parent = self

        self._debug = lgr.isEnabledFor(logging.DEBUG)
        self._debug = True
        self._names = None

    @property
    def full_path(self):
        return tuple(list(self.hierarchy_path) + [self.name])

    @property
    def path_str(self):
        return '->'.join(self.full_path)

    @property
    def depth(self):
        return len(self.hierarchy_path) + 1

    def get_all_names(self, match_options):
        if self._names is None:
            self._names = [self.name] + self.alias
            if match_options.ignore_case:
                self._names = [n.lower() for n in self._names]

            if match_options.longest_name_first:
                self._names.sort(key=lambda n: -len(n))
        return self._names

    def clear_names_cache(self):
        self._names = None

    ## 66% of time is spent in this function.
    def match(self, text, match_options):
        def iter_spans(pattern, text):
            idx, len_pattern = 0, len(pattern)
            while idx != -1:
                idx = text.find(pattern, idx)
                if idx != -1:
                    span = Span(start=idx, end=idx + len_pattern)
                    idx += 1
                    if not match_options.match_on_word_boundary:
                        yield span
                    elif span.on_word_boundary(text, match_options.word_boundary_chars):
                        yield span

        # Ignoring options like word_boundary
        all_spans = []
        for name in self.get_all_names(match_options):
            spans = list(iter_spans(name, text))
            if spans:
                all_spans.extend(spans)
                if self._debug:
                    lgr.debug(f'\t\tMatching level:{self.level} >{name}<*')
            # else:
            #     if self._debug:
            #         lgr.debug(f'\t\tMatching level:{self.level} >{name}<')
                            
                    
        if all_spans:
            spans_str = ", ".join(s.span_str(text) for s in all_spans)                                

            before_len = len(all_spans)
            all_spans = Span.remove_subsumed(all_spans)
            if len(all_spans) != before_len:
                lgr.debug(f"\t\t\t Subsuming Spans removed")
            spans_str = ", ".join(s.span_str(text) for s in all_spans)                    
            lgr.debug(f"\t<matched: node:{self.path_str} spans[{len(all_spans)}]: >{spans_str}<") 
        return all_spans

    def find_adjoin_span_groups(self, span, span_groups, text):
        return [ span_group for span_group in span_groups if span.adjoins(span_group.full_span, text, " (),.;")]

    def find_child_span_groups(self, span, span_groups):
        span_path, child_sgs = self.full_path, []
        path_len = len(span_path)
        for sg in span_groups:
            if sg.hierarchy_path[:path_len] == span_path:
                child_sgs.append(sg)

        if len(child_sgs) > 1:
            child_sgs.sort(key=attrgetter('sum_span_len'), reverse=True)
            k, g = first(it.groupby(child_sgs, key=attrgetter('sum_span_len')))
            return list(g)
        else:
            return child_sgs

    def rec_find_match(self, text, match_options):
        def print_groups(span_groups):
            print(f'>{self.name}< {[len(span_groups)]} {"|".join(str(sg) for sg in span_groups)}')            
            #print(fn'{text} [{len(span_groups)}]')


        #lgr.debug(f"\trec_find_match:{self.name}")

        span_groups = []  # child span_groups
        for child in self.children:
            child_span_groups = child.rec_find_match(text, match_options)
            span_groups.extend(child_span_groups)

        spans = self.match(text, match_options)  # self matches
        
        if spans and span_groups:
            spans_str = ", ".join(f'>{s.span_str(text)}<' for s in spans)
            lgr.debug(f"\t#Handling span_groups[{len(span_groups)}] spans[{len(spans)}]: {spans_str}")
            
            for span in spans:
                # Hierarchy could have two nodes with same names - possible (not ideal)
                # leading to two spans matching the same text, in that case we prefer
                # deeper span, i.e, existing span_group

                can_sgs = [sg for sg in span_groups if not span.overlaps_any(sg.spans)]
                
                if match_options.merge_strategy == 'adjoin':
                    merge_sgs = self.find_adjoin_span_groups(span, can_sgs, text)
                else:
                    merge_sgs = self.find_child_span_groups(span, can_sgs)                
                
                if merge_sgs:
                    lgr.debug(f"\t\t#Multiple merge_sgs")
                    hier_span = HierarchySpan.build(self, span)
                    [ m_sg.add(hier_span) for m_sg in merge_sgs ]
                    lgr.debug(f"\t\t#Merged >{span.span_str(text)}< with {Hierarchy.to_str(merge_sgs)}")
                else:
                    hier_span = HierarchySpan.build(self, span)
                    span_groups.append(HierarchySpanGroup.build(text, hier_span))
                    lgr.debug(f"\t\t#Creating 1 span_group for >{span.span_str(text)}<")
        elif spans:
            assert Span.is_non_overlapping(spans), print_groups([]) 
            hier_spans = [HierarchySpan.build(self, span) for span in spans]
            span_groups = [HierarchySpanGroup.build(text, h) for h in hier_spans]
            lgr.debug(f"\t#Creating {len(span_groups)} new span_groups")

        return span_groups



class HierarchySpanGroup(SpanGroup):
    @classmethod
    def build(cls, text, span):
        return HierarchySpanGroup(spans=[span], text=text)

    @classmethod
    def first_group(cls, span_groups, condition):
        sgs = sorted(span_groups, key=attrgetter(condition), reverse=True)
        k, first_group = first(groupby(sgs, key=attrgetter(condition)), (None, []))
        return list(first_group)

    @classmethod
    def select_non_overlapping(cls, span_groups):
        retain_idxs = [True] * len(span_groups)
        for (idx1, idx2) in it.combinations(range(len(span_groups)), 2):
            m1, m2 = span_groups[idx1], span_groups[idx2]
            if m1.overlaps(m2) and retain_idxs[idx1] and retain_idxs[idx2]:
                min_len, min_idx = min((m1.span_len, idx1), (m2.span_len, idx2))
                retain_idxs[min_idx] = False

        sel_sgs = [m for (idx, m) in enumerate(span_groups) if retain_idxs[idx]]
        return sel_sgs
    
    @classmethod
    def select_sum_inv_span_gap(cls, span_groups):
        return cls.first_group(span_groups, 'sum_inv_span_gap')

    @classmethod
    def select_sum_span_len(cls, span_groups):
        return cls.first_group(span_groups, 'sum_span_len_start')
        #span_groups.sort(key=attrgetter('sum_span_len_start'), reverse=True)
        #return span_groups[:1]

    @classmethod
    def select_sum_matching_len(cls, span_groups):
        return cls.first_group(span_groups, 'sum_match_len')        
        #span_groups.sort(key=attrgetter('sum_match_len'), reverse=True)
        #return span_groups[:1]        

    @classmethod
    def select_deeper(cls, span_groups):
        return cls.first_group(span_groups, 'depth')                
        #span_groups.sort(key=attrgetter('depth'), reverse=True)
        #return span_groups[:1]

    @classmethod
    def select_at_start(cls, span_groups):
        return [sg for sg in span_groups if sg.full_span.start == 0]

    @classmethod
    def select_left_most(cls, span_groups):
        sgs = sorted(span_groups, key=lambda sg: sg.full_span.start )
        k, first_group = first(groupby(sgs, key=lambda sg: sg.full_span.start), (None, []))
        return list(first_group)

    @classmethod
    def select_first(cls, span_groups):
        return span_groups[:1]

    @classmethod
    def select_none(cls, span_groups):
        return span_groups

    @classmethod
    def select_path_match(cls, span_groups, hierarchy_path):
        return [sg for sg in span_groups if sg.has_sub_hierarchy_path(hierarchy_path)]

    @classmethod
    def select_level_match(cls, span_groups, level):
        sgs = span_groups
        return sgs if level == None else [sg for sg in sgs if sg.get_level() == level]

    @classmethod
    def select_connected_sum_span_len(cls, span_groups, min_depth=2):
        sgs = []
        for sg in span_groups:
            print(sg.new_str())
            if sg.is_connected(min_depth):
                sgs.append(sg)
        return cls.select_sum_span_len(sgs)

    @classmethod
    def select_unique(cls, span_groups):
        def uniq_str(sg):
            names = [s.node.name for s in reversed(sg.spans)]            
            return f'{sg.span_str()}-{sg.hierarchy_path}'
        
        text_sgs = [(uniq_str(sg), sg) for sg in span_groups]
        text_sgs.sort(key=lambda tup: tup[0])
        unique_sgs = []
        for k, g in groupby(text_sgs, key=lambda tup: tup[0]):
            unique_sgs.append(first(g)[1])
        return unique_sgs

    @classmethod
    def select(cls, span_groups, strategy):
        lgr.debug(f'\tselect_strategy:{strategy} [{len(span_groups)}]')
        if strategy == 'non_overlapping':
            return cls.select_non_overlapping(span_groups)
        elif strategy == 'at_start':
            return cls.select_at_start(span_groups)
        elif strategy == 'left_most':
            return cls.select_left_most(span_groups)
        elif strategy == 'sum_span_len':
            return cls.select_sum_span_len(span_groups)
        elif strategy == 'first':
            return cls.select_first(span_groups)
        elif strategy == 'none':
            return cls.select_none(span_groups)
        elif strategy == 'sum_matching_len':        
            return cls.select_sum_matching_len(span_groups)
        elif strategy == 'connected_sum_span_len':
            return cls.select_connected_sum_span_len(span_groups)
        else:
            raise NotImplementedError(f'Strategy {strategy} not implemented')
        
    #@classmethod
    #def select_level(cls, span_groups, level):
    #    return [ sg for sg in span_groups if sg.spans[0].node.level == level ]

    @property
    def root(self):
        return self.spans[0].node.hierarchy_path[0]

    @property
    def leaf(self):
        return self.spans[0].node.name

    @property
    def hierarchy_path(self):
        node = self.spans[0].node
        return tuple(chain(node.hierarchy_path, [node.name]))

    @property
    def depth(self):
        return self.spans[0].node.depth

    @property
    def min_depth(self):
        return self.spans[-1].node.depth

    def has_sub_hierarchy_path(self, sub_path):
        path_str = '.'.join(self.hierarchy_path)
        sub_str = '.'.join(sub_path)
        return sub_str.lower() in path_str.lower()

    def get_level(self):
        return self.spans[0].node.level

    def get_label_val(self, label):
        return self.spans[0].node.node_info.get(label, None)

    def is_contiguous(self):
        depths = [span.node.depth for span in reversed(self.spans)]
        return depths == list(range(min(depths), max(depths)+1))

    def is_connected(self, min_depth):
        is_direct = self.get_label_val('direct') is not None
        return (self.min_depth <= min_depth and self.is_contiguous()) or is_direct

    def span_str(self, delim="|"):
        return delim.join(s.span_str(self.text) for s in self.spans)


    def __str__(self):
        names = [s.node.name for s in reversed(self.spans)]
        min_depth = self.spans[-1].depth

        span_str = ", ".join(f"[{s.start}:{s.end}]" for s in self.spans)
        max_span_str = f"[{self.min_start}:{self.max_end}]"

        return f'D:{min_depth} {"->".join(names)} {max_span_str}'

    def new_str(self):
        names = [s.node.name for s in reversed(self.spans)]
        min_depth = self.spans[-1].depth

        span_str = ", ".join(f"[{s.start}:{s.end}]" for s in self.spans)
        max_span_str = f"[{self.min_start}:{self.max_end}]"

        return f'D:{min_depth} #spans:{len(names)} {"->".join(names)} {max_span_str}'
        

class HierarchySpan(Span):
    node: HierarchyNode

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def build(cls, node, span):
        return HierarchySpan(start=span.start, end=span.end, node=node)

    def clone(self):
        return HierarchySpan(self.node)

    @property
    def depth(self):
        return self.node.depth



class Hierarchy:
    ValidKeys = [
        "name",
        "alias",
        "direct",
        "overlap",
        "description",
        "orgCode",
        "expand_names",
        "ignoreLevels",
        "unifyName",
        "multipleHierarchies",
        "defaultHierarchy",
        "unifyStrategy",
        "unifyAttribute"
    ]

    def __init__(self, file_path, noparse_file_path=None, save_unmatched=False):

        self.file_path = Path(file_path)
        if not is_readable(self.file_path):
            raise ValueError(f"Path is not readable: {self.file_path}")

        yml_dict = read_config_from_disk(self.file_path)

        self.ignore_levels = yml_dict.get('ignoreLevels', [])
        self.root = self.rec_build_tree(yml_dict)

        self.noparse_file_path = Path(noparse_file_path) if noparse_file_path else None
        self.noparse_dict = self.read_noparse(noparse_file_path)
        self.save_unmatched = save_unmatched

        self.expand_names_dict = yml_dict.get("expand_names", {})
        if self.expand_names_dict:
            for (old_sub_str, new_sub_str) in self.expand_names_dict.items():
                lgr.info(f'Expanding names >{old_sub_str}< >{new_sub_str}<')
                assert old_sub_str != new_sub_str
                self.expand_names(old_sub_str, new_sub_str)
        self._match_options = None
        self.record_dict = {}

    def rec_build_tree(self, yml_dict, path=[], level=None):
        def get_children(yml_dict):
            keys = yml_dict.keys()
            levels = [l for l in keys if not (l in self.ValidKeys or l[0] == "_")]

            assert len(levels) in (0, 1)

            if levels:
                level = levels[0]
                return yml_dict[level], level
            else:
                return [], None

        def get_info(yml_dict, child_level):
            ignore = ['name', 'alias'] + [child_level]
            return dict((k,v) for (k, v) in yml_dict.items() if k not in ignore)

        children_yml, child_level = get_children(yml_dict)
        name, children = yml_dict["name"], []

        if child_level not in self.ignore_levels:
            for child_yml in children_yml:
                child_path = path + [name]
                child = self.rec_build_tree(child_yml, child_path, child_level)
                children.append(child)
        #

        node_info = get_info(yml_dict, child_level)
        alias = yml_dict.get("alias", [])
        node = HierarchyNode(name, alias, path, level, children, node_info)
        return node

    def expand_names(self, old, new):
        def expand_node_names(node):
            match_options = MatchOptions()
            all_names = node.get_all_names(match_options)
            new_alias = [n.replace(old, new).strip() for n in all_names if old in n]
            node.alias += new_alias
            node._names = None
        self.visit_depth_first(expand_node_names)

    def read_noparse(self, noparse_file_path):
        if not noparse_file_path:
            return {}
        else:
            raise NotImplementedError("Not implemented no parse")

    def find_match_in_sub_hierarchy(self, text, sub_path, match_options):
        lgr.debug(f"find_match_in_sub_hierarchy: {text}")
        sub_node = self.get_node(sub_path, MatchOptions(ignore_case=False))
        assert sub_node

        if self._match_options and self._match_options != match_options:
            lgr.debug('New match options, clearing names')
            self.visit_depth_first(lambda node: node.clear_names_cache())
        self._match_options = match_options

        text = text.lower() if match_options.ignore_case else text                    
        span_groups = sub_node.rec_find_match(text, match_options)

        self.record(text, span_groups)

        return HierarchySpanGroup.select_non_overlapping(span_groups)        
        

    def find_match(self, text, match_options):
        lgr.debug(f"find_match: {text}")

        if self._match_options and self._match_options != match_options:
            lgr.debug('New match options, clearing names')
            self.visit_depth_first(lambda node: node.clear_names_cache())
        self._match_options = match_options

        text = text.lower() if match_options.ignore_case else text                    
        span_groups = self.root.rec_find_match(text, match_options)

        #self.record(text, span_groups)
        #return HierarchySpanGroup.select_non_overlapping(span_groups)

        return HierarchySpanGroup.select(span_groups, match_options.select_strategy)    


    @classmethod
    def to_str(self, span_groups, prefix=''):
        return f'{prefix}{"|".join(str(sg) for sg in span_groups)}'

    def visit_depth_first(self, visit_func):
        def rec_visit(node):
            for child in node.children:
                rec_visit(child)
            visit_func(node)

        rec_visit(self.root)

    def visit_breadth_first(self, visit_func):
        def rec_visit(node):
            visit_func(node)            
            for child in node.children:
                rec_visit(child)

        rec_visit(self.root)

    def record(self, text, span_groups):
        for hier_span in [s for sg in span_groups for s in sg.spans]:
            match_text =  text[hier_span.slice()]
            idx = hier_span.node.get_all_names(self._match_options).index(match_text)
            self.record_dict.setdefault(hier_span.node.full_path, set()).add(idx)

    def write_record(self, record_file_path):
        assert record_file_path != self.file_path

        def print_node(node):
            indent = node.depth * 2 * ' '
            n_str = f'{indent}- name: {node.name}\n'
            assert n_str.isascii()
            record_file.write(f'{indent}- name: {node.name}\n')
            rec_idxs = self.record_dict.get(node.full_path, [])
            enum_names = enumerate(node.get_all_names(self._match_options))
            new_aliases = [a for idx, a in enum_names if idx in rec_idxs ]
            if new_aliases:
                a_str = f'{indent}  alias: [{",".join(new_aliases)}]\n'
                #assert a_str.isascii(), f'{a_str} not ascii'
                record_file.write(a_str)

        with open(record_file_path, 'w', encoding="utf-8") as record_file:
            self.visit_breadth_first(print_node)

        
    def get_node(self, hierarchy_path, match_options):
        def rec_get_node(node, hierarchy_path):
            assert hierarchy_path[0] in node.get_all_names(match_options)
            
            child_hier_path = hierarchy_path[1:]
            if not child_hier_path:
                return node
            child_name = child_hier_path[0]
            for child in node.children:
                if child_name in child.get_all_names(match_options):
                    return rec_get_node(child, child_hier_path)
            return None

        return rec_get_node(self.root, hierarchy_path)
