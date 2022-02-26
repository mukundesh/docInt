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
import itertools as it
import logging


from docint.span import Span, SpanGroup
from docint.util import is_readable, read_config_from_disk

lgr = logging.getLogger(__name__)


@dataclass
class MatchOptions:
    ignore_case: bool = True
    longest_name_first: bool = True


class HierarchyNode:
    def __init__(self, name, alias, hierarchy_path, level, children, node_info):
        self.name = name
        self.alias = alias
        self.hierarchy_path = hierarchy_path
        self.level = level
        self.children = children

        self.node_info = node_info

        self.parent = None
        self.u_parent = None

        for child in self.children:
            child.parent = self

        self._names = None
        lgr.setLevel(logging.INFO)
        
        self._names = None

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
                    yield Span(start=idx, end=idx + len_pattern)
                    idx += 1  # inc to end ? # pal

        #lgr.debug(f"\t\tmatch:{self.name}")
        # Ignoring options like word_boundary
        
        all_spans = []
        for name in self.get_all_names(match_options):
            #lgr.debug(f'\tMatching >{name}<')
            spans = list(iter_spans(name, text))
            if spans:
                #spans_str = ", ".join(s.span_str(text) for s in spans)                
                #lgr.debug(f"\t\t# spans: {len(spans)} name:{name} {spans_str}")
                all_spans.extend(spans)
                
        return all_spans

    def rec_find_match(self, text, match_options):
        #lgr.debug(f"\trec_find_match:{self.name}")

        span_groups = []  # child span_groups
        for child in self.children:
            child_span_groups = child.rec_find_match(text, match_options)
            span_groups.extend(child_span_groups)

        spans = self.match(text, match_options)  # self matches
        if spans and span_groups:
            spans_str = ", ".join(s.span_str(text) for s in spans)
            #lgr.debug(f"\tFound:{self.name} #spans: {len(spans)} {spans_str}")
            for span in spans:
                adjoin_groups = [
                    span_group
                    for span_group in span_groups
                    if span.adjoins(span_group.full_span, text, " (),.;")
                ]
                if adjoin_groups:
                    assert len(adjoin_groups) == 1
                    hier_span = HierarchySpan.build(self, span)
                    adjoin_groups[0].add(hier_span)
                else:
                    hier_span = HierarchySpan.build(self, span)
                    span_groups.append(HierarchySpanGroup.build(text, hier_span))
        elif spans:
            hier_spans = [HierarchySpan.build(self, span) for span in spans]
            span_groups = [HierarchySpanGroup.build(text, h) for h in hier_spans]

        return span_groups


class HierarchySpanGroup(SpanGroup):
    @classmethod
    def build(cls, text, span):
        return HierarchySpanGroup(spans=[span], text=text)

    @property
    def root(self):
        return self.spans[0].node.hierarchy_path[0]

    @property
    def leaf(self):
        return self.spans[0].node.name

    @property
    def hierarchy_path(self):
        hier_path = self.spans[0].node.hierarchy_path
        for hier_span in self.spans[1:]:
            span_idx = hier_path.index(hier_span.name)
            hier_path[span_idx] = f"+{hier_path[span_idx]}"
        hier_path[-1] = f"+{hier_path[-1]}"
        return hier_path

    def __str__(self):
        names = [s.node.name for s in reversed(self.spans)]
        min_depth = self.spans[-1].depth

        span_str = ", ".join(f"[{s.start}:{s.end}]" for s in self.spans)
        max_span_str = f"[{self.min_start}:{self.max_end}]"

        return f'D:{min_depth} {"->".join(names)} {max_span_str}'


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
    ]

    def __init__(self, file_path, noparse_file_path=None, save_unmatched=False):

        self.file_path = Path(file_path)
        if not is_readable(self.file_path):
            raise ValueError(f"Path is not readable: {self.file_path}")

        yml_dict = read_config_from_disk(self.file_path)
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

        def get_info(yml_dict):
            return {}

        children_yml, child_level = get_children(yml_dict)
        name, children = yml_dict["name"], []
        for child_yml in children_yml:
            child_path = path + [name]
            child = self.rec_build_tree(child_yml, child_path, child_level)
            children.append(child)

        node_info = get_info(yml_dict)
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

    def find_match_paths(self, text, match_options):
        return self.find_match(text, match_options)

    def find_match(self, text, match_options):
        lgr.debug(f"find_match_paths: {text}")

        if self._match_options and self._match_options != match_options:
            lgr.debug('clearing names')
            self.visit_depth_first(lambda node: node.clear_names_cache())
        self._match_options = match_options

        text = text.lower() if match_options.ignore_case else text                    
        match_paths = self.root.rec_find_match(text, match_options)

        
        # select which match_paths to save
        retain_idxs = [True] * len(match_paths)
        for (idx1, idx2) in it.combinations(range(len(match_paths)), 2):
            m1, m2 = match_paths[idx1], match_paths[idx2]
            if m1.overlaps(m2) and retain_idxs[idx1] and retain_idxs[idx2]:
                min_len, min_idx = min((m1.span_len, idx1), (m2.span_len, idx2))
                retain_idxs[min_idx] = False

        match_paths = [m for (idx, m) in enumerate(match_paths) if retain_idxs[idx]]
        return match_paths

    def visit_depth_first(self, visit_func):
        def rec_visit(node):
            for child in node.children:
                visit_func(child)
            visit_func(node)

        rec_visit(self.root)
