from typing import List
import logging
from pathlib import Path

from ..vision import Vision
from ..hierarchy import Hierarchy, MatchOptions
from ..region import Region, TextConfig
from ..extracts.orgpedia import Post

from ..util import is_readable, read_config_from_disk

#lgr = logging.getLogger(__name__)


class PostInfo(Region):
    continues: List[Post] = []
    relinquishes: List[Post] = []            
    assumes: List[Post] = []
    detail_idx: int # TODO please remove this, this is not inc correctly
    ordered_annots: str
    is_valid: bool = True
    error: str = ''

    @classmethod
    def build(cls, words, continues, relinquishes, assumes, detail_idx):
        return PostInfo(words=words, word_lines=[words], continues=continues,
                        relinquishes=relinquishes, assumes=assumes,
                        detail_idx=detail_idx, ordered_annots='')

    @classmethod
    def build_invalid(cls, words, detail_idx, error_str):
        return PostInfo(words=words, word_lines=[words], continues=[],
                        relinquishes=[], assumes=[], detail_idx=detail_idx,
                        ordered_annots='', is_valid=False, error=error_str)


def get_posts_types(annot_str, match_paths_dict):
    verb = 'continues'
    
    verb_dict = {'continues': [], 'relinquishes': [], 'assumes': []}
    verb_found = {'continues': False, 'relinquishes': False, 'assumes': False}
    
    rm, dm = -1, -1
    for annot in annot_str.split('-'):
        if not annot:
            print(f'AnnotEmptyError: {annot_str}')
            return [], 'AnnotEmptyError'
            
        if annot[0] == 'V':
            a1 = annot[1]
            verb = 'continues' if a1 == 'c' else 'relinquishes' if a1 == 'r' else 'assumes'
            verb_found[verb] = True
        else:
            verb_dict[verb].append(annot)
            idx = int(annot[1])
            (rm, dm) = (max(rm,idx), dm) if annot[0] == 'R' else (rm, max(dm,idx))
    #end

    if annot_str[0] != 'V':
        verb_found['continues'] = True

    if not all( bool(a) == f for (a,f) in zip(verb_dict.values(), verb_found.values()) ):
        #print(f'AnnotMissingError: {annot_str}')
        return [], 'AnnotMissingError'

    n_roles, n_depts = len(match_paths_dict['role']), len(match_paths_dict['dept'])

    #print(f'roles: rm {rm} # {n_roles} depts dm {dm} # {n_depts}')
    
    if rm + 1 != n_roles:
        #print(f'RoleIndexError: {annot_str} idx:{rm} #roles: {n_roles}')
        return [], 'RoleIndexError'
        
    if dm +1 !=  n_depts or (rm +1 > n_depts):
        #print(f'DeptIndexError: {annot_str} idx:{dm} #depts: {n_depts}')
        return [], f'DeptIndexError {annot_str}'

    actual = [ sorted(list(set(int(a[1]) for a in annots))) for annots in verb_dict.values() ]
    return actual, ''

@Vision.factory(
    "post_parser_onsentence",
    default_config={
        "doc_confdir": "conf",
        "hierarchy_files": {
            "dept": "dept.yml",            
            "role": "role.yml",
            "verb": "verb.yml",
        },
        "ordered_annots_file": "ordered_annots.yml",
        "ignore_labels": ["ignore"],
    },
)

class PostParserOnSentence:
    def __init__(self, doc_confdir, hierarchy_files, ordered_annots_file, ignore_labels):
        self.doc_confdir = Path(doc_confdir)
        self.hierarchy_files = hierarchy_files
        self.ordered_annots_file = Path(ordered_annots_file)
        self.ignore_labels = ignore_labels

        self.hierarchy_dict = {}
        for field, file_name in self.hierarchy_files.items():
            hierarchy_path = self.doc_confdir / file_name
            hierarchy = Hierarchy(hierarchy_path)
            self.hierarchy_dict[field] = hierarchy

        self.match_options = MatchOptions(ignore_case=True)
        self.text_config = TextConfig(rm_labels=self.ignore_labels)

        ordered_annots_path = self.doc_confdir / self.ordered_annots_file
        yml_map = read_config_from_disk(ordered_annots_path)
        self.ordered_annots = yml_map['ordered_annots']
        self.ignored_annots = yml_map.get('ignored_annots', [])


        self.lgr = logging.getLogger(__name__ + ".")
        self.lgr.setLevel(logging.DEBUG)
        self.lgr.addHandler(logging.StreamHandler())

    def mark_in_region(self, post_region, post_type, dept_match_path, role_match_path):
        for span in dept_match_path.spans:
            label = f'post-dept-{post_type}'
            post_region.add_span(span[0], span[1], label, self.text_config)

        if not role_match_path:
            return

        for span in role_match_path.spans:
            label = f'post-role-{post_type}'
            post_region.add_span(span[0], span[1], label, self.text_config)
        

    def build_post_info(self, post_region, post_str, post_words, match_paths_dict, detail_idx):
        annots, dept_role_spans = [], []
        post_types = ['continues', 'relinquishes', 'assumes']
        for field, match_paths in match_paths_dict.items():
            match_paths.sort(key=lambda m: m.min_start)

            span_pairs = [ m.full_span for m in match_paths ]            
            esp, ps = list(enumerate(span_pairs)), post_str
            if field == "verb":
                annots += [(s, f"V{ps[s:e][0].lower()}{i}") for (i, (s, e)) in esp]
                [ post_region.add_span(s, e, 'verb', self.text_config) for (i, (s, e)) in esp]
            else:
                annots += [(s, f"{field[0].upper()}{i}") for (i, (s, e)) in esp]
                dept_role_spans += [ (field, (s,e)) for (i, (s,e)) in esp ]
        annots.sort()
        ordered_annot_str = "-".join(a for (s, a) in annots)

        post_idxs_types, err_str = get_posts_types(ordered_annot_str, match_paths_dict)

        if err_str:
            self.lgr.debug(f'*** {ordered_annot_str} {post_str} {err_str}')
            [ post_region.add_span(s, e, f'post-{field}-continues', self.text_config) for (field, (s,e)) in dept_role_spans]
            return PostInfo.build_invalid(post_words, detail_idx, err_str)
        else:
            self.lgr.debug(f'{ordered_annot_str} {post_idxs_types} {post_str}')

        types_posts = []
        for post_type, post_idxs in zip(post_types, post_idxs_types):
            type_posts = []
            for idx in post_idxs:
                dept_match_path = match_paths_dict["dept"][idx]
                if len(match_paths_dict["role"]) > idx:
                    role_match_path = match_paths_dict["role"][idx]
                else:
                    role_match_path = None
                    
                post = Post.build(post_words, post_str, dept=dept_match_path, role=role_match_path)
                self.mark_in_region(post_region, post_type, dept_match_path, role_match_path)
                type_posts.append(post)
            types_posts.append(type_posts)

        post_info = PostInfo.build(post_words, types_posts[0], types_posts[1],
                                   types_posts[2], detail_idx)
        return post_info

    def parse(self, post_region, post_str, detail_idx):
        match_paths_dict = {}

        for (field, hierarchy)  in self.hierarchy_dict.items():
            match_paths = hierarchy.find_match_paths(post_str, self.match_options)
            match_paths_dict[field] = match_paths
            self.lgr.debug(f'{field}: {post_str}')
            [ self.lgr.debug(f'\t{str(mp)}') for mp in match_paths ]
        # end for

        post_words = [ w for idx, w in post_region.iter_words(self.text_config)]

        post_info = self.build_post_info(post_region, post_str, post_words, match_paths_dict, detail_idx)
        return post_info


    def check_span_groups(posts_groups_dict):
        annot_str = get_annot_str(posts_groups_dict)

        
        if all(len(post_groups) for post_groups in posts_groups_dict.values()):
            return False, f'EmptyPostType: {annot_str}'

        for post_groups in posts_groups_dict.values():
            num_depts = len(p for p in post_groups if p.root == 'dept')
            num_roles = len(p for p in post_groups if p.root == 'role')

            if num_roles > num_depts:
                return False, 'MismatchDeptError: {annot_str}'
            
        return True, ''


    def edit_span_groups(posts_groups_dict):
        continues = posts_groups_dict.get('continues', [])
        relinquishes = posts_groups_dict.get('relinquishes', [])

        if not (continues and relinquishes):
            return 

        c_depts = [ p.leaf for p in continues if p.root == 'dept' ]
        r_depts = [ p.leaf for p in relinquishes if p.root == 'dept' ]

        del_idxs = [ idx for (idx, dept) in enumerate(c_depts) if dept in r_depts]

        new_continues = [ p for (idx, p) in enumerate(continues) if idx in del_idxs]
        posts_groups_dict['continues'] = new_continues
        


    def build_post_info2(self, post_region, hier_span_groups):
        verb, posts_groups_dict = 'continues', {}
        for hier_span_group in hier_span_groups:
            if hier_span_group.root == 'verb':
                verb = hier_span_group.leaf
            else:
                posts_groups_dict.setefault(verb, []).appennd(hier_span_group)
        #end for

        is_valid, err_str = check_groups(posts_groups_dict)
        if not is_valid:
            return PostInfo.build_invalid(post_region.words, detail_idx, err_str)

        posts_dict = {'continues': [], 'relinquishes':[], 'assumes':[]}
        for post_type,  hier_span_groups in posts_groups_dict.items():
            role = None
            for hier_span_group in hier_span_groups:
                if hier_span_group.root == 'role':
                    role = hier_span_group
                else:
                    dept = hier_span_group
                    post_words = get_words(post_region, dept, role)
                    posts_dict[posts_type].append(Post.build(post_words, dept, role))
                    dept, role = None, None
        #end for
        post_info = PostInfo.build(post_region.words, detail_idx, **post_dict)
        return post_info
                

        
        

    

    def __call__(self, doc):
        self.lgr.info(f"post_parser: {doc.pdf_name}")        
        
        doc.add_extra_page_field("post_infos", ('list', __name__, "PostInfo"))
        for page in doc.pages:
            page.post_infos = []
            for postinfo_idx, list_item in enumerate(page.list_items):
                
                # TODO Should we remove excess space and normalize it ? worthwhile...
                post_str = list_item.line_text(self.text_config)
                self.lgr.debug(list_item.str_spans())
                post_info = self.parse(list_item, post_str, postinfo_idx)
                page.post_infos.append(post_info)
        return doc
