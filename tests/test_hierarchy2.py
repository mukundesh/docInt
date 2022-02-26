import logging
import sys

from docint.hierarchy2 import Hierarchy, MatchOptions

l1 = "prime minister has assumed the office of Home Ministry"
m1 = "D:2 Prime Minister [0:14]"

l2 = "Shri xxx yyy has relinquished the Minister of State of Home Ministery and assumed the charnge of Minister of State (Independent Charge) of Home Ministry"
m2 = 'D:4 Minister of State [34:51], D:3 Minister of State (Independent Charge) [97:135]'


l3 = 'Shri M.O.H. Farook relinquished the office of Minister of State in the Ministry of Civil Aviation and Tourism and assumed the office of Minister of State in the Ministry of Civil Aviation and Tourism (Department of Civil Aviation).'
m3 = 'D:2 Ministry of Civil Aviation and Tourism->Department of Civil Aviation [161:229], D:2 Ministry of Civil Aviation and Tourism [71:109]'

l4 = 'Shri Radha Mohan Singh, Minister of Agriculture and Farmers Welfare assumed the additional charge of the office of the Minister of Consumer Affairs, Food and Public Distribution'

l5 = 'Kum. Mamta Banerjee, Minister of State in the Ministry of Human Resource Development (Department of Youth Affairs and Sports) also assumed additional charge of the office of Minister of State in the Ministry of Human Resource Development (Department of Women and Child Development)'
m5 = 'D:2 Ministry of Human Resource Development->Department of Youth Affairs and Sports [46:124], D:2 Ministry of Human Resource Development->Department of Women and Child Development [199:280]'


l6 = 'Shri P.A. Sangma relinquished the office of the Minister of State (Independent charge) of the Ministry of Labour and assumed the office of the Minister of Labour '
m6 = 'D:2 Ministry of Labour [94:112], D:2 Ministry of Labour [143:161]'

l7 = 'Shri Dinesh Singh relinquished the office of Minister of Water of Resources and assumed the office of Minister Commerce'
m7 = 'D:2 Ministry of Commerce [111:119], D:2 Ministry of Drinking Water and Sanitation [57:75]'


def eval_text(text):
    dept_hierarchy = Hierarchy("cabsec_dept.yml")
    match_paths = dept_hierarchy.find_match_paths(text, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    sys.exit(1)
    
def eval_role_text(text):
    text = ' '.join(text.split())
    dept_hierarchy = Hierarchy("cabsec_role.yml")
    match_paths = dept_hierarchy.find_match_paths(text, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    sys.exit(1)


def perf_test():
    dept_hierarchy = Hierarchy("cabsec_dept.yml")
    ignore_case = MatchOptions(ignore_case=True)
    respect_case = MatchOptions(ignore_case=False)    

    for i in range(300):
        match_paths = dept_hierarchy.find_match_paths(l3, ignore_case)
        match_paths = dept_hierarchy.find_match_paths(l5, ignore_case)
        match_paths = dept_hierarchy.find_match_paths(l6, ignore_case)
        match_paths = dept_hierarchy.find_match_paths(l7, ignore_case)
        
    role_hiearchy = Hierarchy("cabsec_role.yml")
    for i in range(300):    
        match_paths = role_hiearchy.find_match_paths(l1, ignore_case)
        match_paths = role_hiearchy.find_match_paths(l1, respect_case)
        match_paths = role_hiearchy.find_match_paths(l2, ignore_case)
    
    



if __name__ == "__main__":
    ignore_case = MatchOptions(ignore_case=True)

    hierarchy_logger = logging.getLogger('docint.hierarchy2')
    hierarchy_logger.setLevel(logging.INFO)
    
    hierarchy_logger.addHandler(logging.StreamHandler())

    if len(sys.argv) > 1 and sys.argv[1] == 'perf':
        num_count = int(sys.argv[2])
        print(f'Running for: {num_count}')
        for idx in range(num_count):
            perf_test()

    if len(sys.argv) == 2:
        eval_text(sys.argv[1])

    if len(sys.argv) == 3:
        eval_role_text(sys.argv[1])

    dept_hierarchy = Hierarchy("cabsec_dept.yml")

    print('\nD: Testing dept with new level added')
    match_paths = dept_hierarchy.find_match_paths(l3, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m3 == match_paths_str, f'Unmatched >{m3}< != >{match_paths_str}<'    
    

    print('\nD: Testing dept with two levels same parent')
    match_paths = dept_hierarchy.find_match_paths(l5, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m5 == match_paths_str, f'Unmatched >{m5}< != >{match_paths_str}<'

    print('\nD: Testing dept occuring twice')
    match_paths = dept_hierarchy.find_match_paths(l6, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m6 == match_paths_str, f'Unmatched >{m6}< != >{match_paths_str}<'

    print('\nD: Testing two depts')    
    match_paths = dept_hierarchy.find_match_paths(l7, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m7 == match_paths_str, f'Unmatched >{m7}< != >{match_paths_str}<'


    role_hiearchy = Hierarchy("cabsec_role.yml")
    print('\nD: Testing single role')        
    match_paths = role_hiearchy.find_match_paths(l1, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m1 == match_paths_str, f'Unmatched >{m1}< != >{match_paths_str}<'

    print('\nD: Testing single role in case sensitive')            
    respect_case = MatchOptions(ignore_case=False)
    match_paths = role_hiearchy.find_match_paths(l1, respect_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert '' == match_paths_str, f'Unmatched >< != >{match_paths_str}<'

    ignore_case = MatchOptions(ignore_case=True)    
    match_paths = role_hiearchy.find_match_paths(l2, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m2 == match_paths_str, f'Unmatched >{m2}< != >{match_paths_str}<'


