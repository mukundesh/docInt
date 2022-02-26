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

from docint import is_readable, read_config_from_disk

lgr = logging.getLogger(__name__)

@dataclass
class MatchOptions:
    ignore_case: bool = True
    longest_name: bool = True



class MatchedPath:
    def __init__(self, node, text, span):
        lgr.debug(f'\t\t\t:Creating MatchedPath')                
        self.nodes = [node]
        self.text = text
        self.spans_ = [span]

    def add(self, node, span):
        # not calcluating overlapping, contiguous
        self.nodes.append(node)
        self.spans_.append(span)
        return self

    def get_hpath(self):
        def rec_add_parent(node, node_list=[]):
            node_list.append(node)
            if node.parent is not None:
                rec_add_parent(node.parent, node_list)
            return node_list
        
        node_list = rec_add_parent(self.nodes[0])
        hpath = [ n.name for n in node_list ]
        #print("=>".join(hpath))
        return hpath

    @property
    def spans(self):
        return self.spans_

    @property
    def span_len(self):
        return self.max_end - self.min_start

    @property
    def min_start(self):
        return min([s for s, e in self.spans_])

    @property
    def max_end(self):
        return max([e for s, e in self.spans_])

    @property
    def full_span(self):
        return (self.min_start, self.max_end)
    

    def __str__(self):
        names = [n.name for n in reversed(self.nodes)]
        min_depth = min([n.depth for n in self.nodes])
        span_str = ", ".join(f"[{s}:{e}]" for s, e in self.spans_)
        max_span_str = f'[{self.min_start}:{self.max_end}]'

        return f'D:{min_depth} {"->".join(names)} {max_span_str}'

    def __len__(self):
        return len(self.nodes)

    @classmethod
    def overlaps(cls, mp1, mp2):
        (s1s, s1e) = (mp1.min_start, mp1.max_end)
        (s2s, s2e) = (mp2.min_start, mp2.max_end)
        
        min_end, max_start = min(s1e, s2e), max(s1s, s2s)
        overlap = max(0, min_end - max_start)
        return True if overlap > 0 else False


class HierarchyNode:
    def __init__(self, name, alias, depth, level, children, node_info):
        self.name = name
        self.alias = alias
        self.depth = depth
        self.level = level
        self.children = children

        self.node_info = node_info

        self.parent = None
        self.u_parent = None

        for child in self.children:
            child.parent = self

        self._names = None
        lgr.setLevel(logging.INFO)

    def get_all_names(self, match_options):
        if self.name is not None:
            self._names = [self.name] + self.alias
            if match_options.ignore_case:
                self._names =  [n.lower() for n in self._names]

            if match_options.longest_name:
                self._names.sort(key=lambda n: -len(n))
                
        return self._names

    def match(self, text, match_options):
        def iter_spans(pattern, text):
            idx, len_pattern = 0, len(pattern)
            while idx != -1:
                idx = text.find(pattern, idx)
                if idx != -1:
                    yield (idx, idx + len_pattern)
                    idx += 1 # inc to end ? # pal
        
        lgr.debug(f'\t\tmatch:{self.name}')
        text = text.lower() if match_options.ignore_case else text

        # Ignoring options like word_boundary
        all_spans = []
        for name in self.get_all_names(match_options):
            #lgr.debug(f'\t\t\tMatching >{name}<')
            spans = [ span for span in iter_spans(name, text) ]
            if spans:
                span_str = ", ".join(f"[{s}:{e}] {text[s:e]}" for s, e in spans)
                lgr.debug(f'\t\t# spans: {len(spans)} {span_str}')
                all_spans.extend(spans)
                
        if all_spans:
            return True, all_spans
        else:
            return False, None

    def rec_find_match_paths(self, text, match_options):
        def is_adjoin(span1, span2):
            (s1s, s1e), (s2s, s2e) = span1, span2
            min_end, max_start = min(s1e, s2e), max(s1s, s2s)
            overlap = max(0, min_end - max_start)
            gap = max_start - min_end
            if overlap > 0:
                return False
            else:
                gs, ge = min(max_start, min_end), max(max_start, min_end)
                gap_text = text[gs:ge]
                gap_text = gap_text.strip(' ().,;')
                #print(f'\t\t\t\tGap:{gap_text} [{gs}:{ge}]')
                return True if gap_text == '' else False

        
        lgr.debug(f'\trec_find_match:{self.name}')
        child_match_paths = []
        for child in self.children:
            c_paths = child.rec_find_match_paths(text, match_options)
            #print(f'** c_path: {len(c_paths)}')
            child_match_paths.extend(c_paths)

        found_match, matched_spans = self.match(text, match_options)
        if found_match:
            span_str = ', '.join(f'{text[s:e]}[{s}:{e}]' for s, e in matched_spans)
            lgr.debug(f'\t\tFound:{self.name} #spans: {len(matched_spans)} {span_str}')
            if child_match_paths:
                for m in matched_spans:
                    adjoin_path = [ c for c in child_match_paths if is_adjoin(m, c.full_span) ]
                    if adjoin_path:
                        assert len(adjoin_path) == 1
                        adjoin_path[0].add(self, m)
                    else:
                        child_match_paths.append(MatchedPath(self, text, m)) 
                        
                #print(f'** child_match_paths: {len(child_match_paths)}')                        
                return child_match_paths
            else:
                m_paths = [ MatchedPath(self, text, span) for span in matched_spans ]
                #print(f'** m_paths: {len(m_paths)}')                                        
                return m_paths
        else:
            #print(f'** child_match_paths: {len(child_match_paths)                                     
            return child_match_paths


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
                assert old_sub_str != new_sub_str
                self.expand_names(old_sub_str, new_sub_str)

    def rec_build_tree(self, yml_dict, depth=1, level=None):
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
        children = []
        for child_yml in children_yml:
            child = self.rec_build_tree(child_yml, depth + 1, child_level)
            children.append(child)

        node_info = get_info(yml_dict)
        node = HierarchyNode(
            yml_dict["name"],
            yml_dict.get("alias", []),
            depth,
            level,
            children,
            node_info,
        )
        return node

    def expand_names(self, old_sub_str, new_sub_str):
        def expand_node_names(node):
            match_options = MatchOptions()
            all_names = node.get_all_names(match_options)
            new_alias = [n.replace(old_sub_str, new_sub_str) for n in all_names]
            node.alias += new_alias

        self.visit_depth_first(expand_node_names)

    def read_noparse(self, noparse_file_path):
        if not noparse_file_path:
            return {}
        else:
            raise NotImplementedError("Not implemented no parse")

    def find_match_paths(self, text, match_options):
        lgr.debug(f'find_match_paths: {text[:30]}...')
        match_paths = self.root.rec_find_match_paths(text, match_options)
        #print(f'Found: {len(match_paths)}')
        #print(', '.join(str(m) for m in match_paths))

        retain_idxs = [True] * len(match_paths)
        for (idx1, idx2) in it.combinations(range(len(match_paths)), 2):
            m1, m2 = match_paths[idx1], match_paths[idx2]
            if MatchedPath.overlaps(m1, m2) and retain_idxs[idx1] and retain_idxs[idx2]:
                #print(f'Overlaps {str(m1)} {str(m2)}')
                min_len, min_idx = min((m1.span_len, idx1), (m2.span_len, idx2))
                retain_idxs[min_idx] = False
            else:
                pass
                #print(f'NoOverlaps {str(m1)} {str(m2)}')

        match_paths = [ m for (idx, m) in enumerate(match_paths) if retain_idxs[idx] ]
        
        #print(f'Retained: {len(match_paths)}')
        #print(', '.join(str(m) for m in match_paths))
                
        return match_paths

    def visit_depth_first(self, visit_func):
        def rec_visit(node):
            for child in node.children:
                visit_func(child)
            visit_func(node)

        rec_visit(self.root)
