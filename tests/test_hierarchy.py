import logging
import sys

from docint.hierarchy import Hierarchy, MatchOptions
from docint.span import Span, SpanGroup

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

l8 = 'Dr. Jitendra Singh relinquished the charge of the office of the Minister of State (Independent Charge) of the Ministry of Youth Affairs and Sports. He will continue to hold the charge of the office of the Minister of State (Independent Charge) of the Ministry of Development of North Eastern Region; Minister of State in the Prime Ministers Office; Minister of State in the Ministry of Personnel Public Grievances and Pensions; Minister of State in the Department of Atomic Energy; and Minister of State in the Department of Space.'
md8 = 'D:2 Ministry of Personnel Public Grievances and Pensions [386:427], D:2 Ministry of Youth Affairs and Sports [110:146], D:2 Ministry of Development of North Eastern Region [251:298], D:2 Prime Ministers Office [325:347], D:2 Department of Space [512:531], D:2 Department of Atomic Energy [454:481]'

md8='D:2 Ministry of Personnel Public Grievances and Pensions [374:426], D:2 Ministry of Youth Affairs and Sports [110:146], D:2 Ministry of Development of North Eastern Region [251:298], D:2 Prime Ministers Office [325:347], D:2 Department of Space [511:530], D:2 Department of Atomic Energy [453:480]'

mr8 = 'D:4 Minister of State [300:317], D:4 Minister of State [349:366], D:4 Minister of State [428:445], D:4 Minister of State [486:503], D:3 Minister of State (Independent Charge) [64:102], D:3 Minister of State (Independent Charge) [205:243]'

u8 = 'Dr. Jitendra Singh relinquished the charge of the office of the - of the -. He will continue to hold the charge of the office of the - of the -; - in the -; - in the -; - in the -; and - in the '


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
        match_paths = dept_hierarchy.find_match(l3, ignore_case)
        match_paths = dept_hierarchy.find_match(l5, ignore_case)
        match_paths = dept_hierarchy.find_match(l6, ignore_case)
        match_paths = dept_hierarchy.find_match(l7, ignore_case)
        
    role_hiearchy = Hierarchy("cabsec_role.yml")
    for i in range(300):    
        match_paths = role_hiearchy.find_match(l1, ignore_case)
        match_paths = role_hiearchy.find_match(l1, respect_case)
        match_paths = role_hiearchy.find_match(l2, ignore_case)


if __name__ == "__main__":
    ignore_case = MatchOptions(ignore_case=True)

    hierarchy_logger = logging.getLogger('docint.hierarchy')
    hierarchy_logger.setLevel(logging.DEBUG)
    
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
    print(l3)

    print('\n- Testing dept with new level added')
    match_paths = dept_hierarchy.find_match(l3, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m3 == match_paths_str, f'\nExp:{m3}\nAct:{match_paths_str}'    
    

    print('\nD: Testing dept with two levels same parent')
    match_paths = dept_hierarchy.find_match(l5, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m5 == match_paths_str, f'Unmatched >{m5}< != >{match_paths_str}<'

    print('\nD: Testing dept occuring twice')
    match_paths = dept_hierarchy.find_match(l6, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m6 == match_paths_str, f'Unmatched >{m6}< != >{match_paths_str}<'

    print('\nD: Testing two depts')    
    match_paths = dept_hierarchy.find_match(l7, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m7 == match_paths_str, f'Unmatched >{m7}< != >{match_paths_str}<'


    role_hiearchy = Hierarchy("cabsec_role.yml")
    print('\nD: Testing single role')        
    match_paths = role_hiearchy.find_match(l1, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m1 == match_paths_str, f'Unmatched >{m1}< != >{match_paths_str}<'

    print('\nD: Testing single role in case sensitive')            
    respect_case = MatchOptions(ignore_case=False)
    match_paths = role_hiearchy.find_match(l1, respect_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert '' == match_paths_str, f'Unmatched >< != >{match_paths_str}<'

    ignore_case = MatchOptions(ignore_case=True)    
    match_paths = role_hiearchy.find_match(l2, ignore_case)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)
    assert m2 == match_paths_str, f'Unmatched >{m2}< != >{match_paths_str}<'

    print('blank out span groups')
    dept_match_paths = dept_hierarchy.find_match(l8, ignore_case)
    dept_match_paths_str = ", ".join(str(m) for m in dept_match_paths)
    print(dept_match_paths_str)
    assert md8 == dept_match_paths_str, f'\nAct:{dept_match_paths_str}\nExp:{md8}'

    blank_l8 = SpanGroup.blank_text(dept_match_paths, l8)    
    role_match_paths = role_hiearchy.find_match(blank_l8, ignore_case)
    role_match_paths_str = ", ".join(str(m) for m in role_match_paths)
    print(role_match_paths_str)
    assert mr8 == role_match_paths_str, f'\nAct:{role_match_paths_str}\nExp:{mr8}'

    all_span_groups = dept_match_paths + role_match_paths
    all_spans = [ s for sg in all_span_groups for s in sg.spans ]
    unmatched = Span.unmatched_texts(all_spans, l8)
    unmatched_str = '-'.join(unmatched)

    print(f'Blanked: {unmatched_str}')
    assert unmatched_str == u8, f'\nAct:{unmatched_str}\nExp:{u8}'


    print('\n- Testing merge strategy=child_span')            
    child_span_option = MatchOptions(merge_strategy='child_span')
    rp_juri_hierarchy = Hierarchy("rajpol_juri.yml")
    
    comm_post_str = 'ACP ADRASH NAGAR JAIPUR POLICE (EAST)'
    match_paths = rp_juri_hierarchy.find_match(comm_post_str, child_span_option)
    match_paths_str = ", ".join(str(m) for m in match_paths)
    print(match_paths_str)

    assert match_paths_str == 'D:3 JAIPUR COMMISSIONERATE->JAIPUR EAST->ADARSH NAGAR [4:36]'
    
    


