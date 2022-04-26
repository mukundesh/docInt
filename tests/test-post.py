import logging
import sys
from pathlib import Path
import json

from more_itertools import first, last

from docint.hierarchy import Hierarchy, MatchOptions
from docint.span import Span
from docint.pipeline import PostParser
from docint.util import read_config_from_disk

Fields = ['role', 'dept', 'juri', 'loca', 'stat']

def eval_field(field, text):
    ignore_case = MatchOptions(ignore_case=True)    
    dept_hierarchy = Hierarchy(f"rajpol_{field}.yml")
    match_paths = dept_hierarchy.find_match_paths(text, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    sys.exit(1)

def get_parser():
    hierarchy_files = {
        "dept": "dept.yml",
        "role": "role.yml",
        "juri": "juri.yml",
        "loca": "loca.yml",
        "stat": "stat.yml",                        
    }
    return PostParser("conf", hierarchy_files, "post.noparse.short.yml", ["ignore"], "postparser")

def eval_pdfpost(text):
    post_parser = get_parser()
    post_parser._enable_hierarchy_logger()
    post = post_parser.parse([], text,  0)

    post_info = dict((f, list(reversed(getattr(post, f'{f}_hpath')))) for f in Fields if getattr(post, f'{f}_hpath'))
    print(post_info)

    return post

NoparseFile = "/Users/mukund/Software/goiConf/Datasets/rajapoli/post.noparse.yml"
NoparseFile = "/Users/mukund/orgpedia/rajpol/flow/R.P.S/text/readPDF_/conf/post.noparse.short.yml"
def eval_prev_version(jsonlFilePath):
    jsonlFilePath = Path(jsonlFilePath)
    jsonLines = jsonlFilePath.read_text().split('\n')
    post_parser = get_parser()
    post_parser.lgr.setLevel(logging.ERROR)
    
    noparse_dict = read_config_from_disk(NoparseFile)
    ignore_posts = ['ADDL SP L/R CIVIL RIGHTS CID CB JAIPUR']
    wrong_posts = ['ADDL SP APO JAIPUR RANGE JAIPUR', 'ADDL SP L/R JAIPUR RANGE JAIPUR', 'ADDL.SP.AJMER RURAL AJMER', 'ADDL.SP.AJMER-CITY AJMER', 'ADDL.SP.AJMER-RURAL AJMER', 'ADDL.SP.APO IGP JAIPUR RANGE JAIPUR', 'ADDL.SP.KOTA CITY KOTA', 'CIRCLE AJMER RURAL AJMER', 'CIRCLE JHUNJHUNU-RURAL JHUNJHUNU']
    noparse_posts = set([p['post'] for p in noparse_dict['posts']] + ignore_posts + wrong_posts) 

    err_idx = 1
    for idx, line in enumerate(jsonLines):
        if not line:
            continue
        
        post_info = json.loads(line)
        post_str = post_info['postStr']

        dept_path_str = '.'.join(post_info['deptPath']).lower()
        if  (post_str in noparse_posts) or ('hq' in post_str.lower()):# or ('terrorist' in dept_path_str):
            if post_str in noparse_posts:
                print(f'==noparse {post_str}')
            continue
        
        post = post_parser.parse([], post_str, idx)
        res, err_count = [ f'{err_idx}:{post_str}'], 0
        
        for field in ['dept', 'role', 'juri']:
            exp_path = post_info[f'{field}Path']
            act_path = getattr(post, f'{field}_hpath', [])
            
            
            exp_path = list(reversed([n.replace('-','') for n in exp_path]))
            err_val = '*' if exp_path != act_path else ' '
            err_count += 1 if err_val == '*' else 0
            f_str = f'{field}{err_val}'
            
            #res.append(f'{idx}-{f_str:5}: {last(exp_path,""):40}|{last(act_path,"")}')
            res.append(f'{idx}-{f_str:5}: {str(exp_path):80}|{act_path}=={post_str}')            
        if err_count > 0:
            print('\n'.join(res))
            print('---------')
            err_idx += 1
    #end for

        



if __name__ == "__main__":
    # hierarchy_logger = logging.getLogger('docint.hierarchy')
    # hierarchy_logger.setLevel(logging.DEBUG)
    # hierarchy_logger.addHandler(logging.StreamHandler())

    # if len(sys.argv) != 3:
    #     print('Usage: {sys.argv[0]} <field> <poststr>')
    #     sys.exit(1)

    #eval_field(sys.argv[1], sys.argv[2])

    if len(sys.argv) != 3 or sys.argv[1] not in ('-f', '-p'):
        print(f'Usage: {sys.argv[0]} [-p|-f] <post_arg>')
        sys.exit(1)

    if sys.argv[1] == '-f':
        eval_prev_version(sys.argv[2])
    else:
        eval_pdfpost(sys.argv[2])

        

    



        
