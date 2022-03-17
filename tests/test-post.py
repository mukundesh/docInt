import logging
import sys

from docint.hierarchy import Hierarchy, MatchOptions
from docint.span import Span
from docint.pipeline import PostParser


def eval_text(field, text):
    ignore_case = MatchOptions(ignore_case=True)    
    dept_hierarchy = Hierarchy(f"rajpol_{field}.yml")
    match_paths = dept_hierarchy.find_match_paths(text, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    sys.exit(1)

def eval_post2(text):
    hierarchy_files = {
        "dept": "dept.yml",
        "role": "role.yml",
        "juri": "juri.yml",
        "loca": "loca.yml",
        "stat": "stat.yml",                        
    }
    
    post_parser = PostParser("conf", hierarchy_files, ["ignore"], "postparser")
    post_parser.parse([], text,  0)



if __name__ == "__main__":
    # hierarchy_logger = logging.getLogger('docint.hierarchy')
    # hierarchy_logger.setLevel(logging.DEBUG)
    # hierarchy_logger.addHandler(logging.StreamHandler())

    # if len(sys.argv) != 3:
    #     print('Usage: {sys.argv[0]} <field> <poststr>')
    #     sys.exit(1)

    #eval_text(sys.argv[1], sys.argv[2])
    eval_post2(sys.argv[1])
    
        

    



