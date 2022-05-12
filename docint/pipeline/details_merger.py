import logging
import sys
from pathlib import Path
from statistics import mean, median

from dataclasses import dataclass, field
from operator import attrgetter
from itertools import product


from polyleven import levenshtein
from more_itertools import first


from ..vision import Vision


# from ..extracts.orgpedia import Officer, OrderDetail, OfficerID
# from ..extracts.orgpedia import OfficerIDNotFoundError

# from ..util import find_date, load_config, read_config_from_disk
# from ..region import DataError, UnmatchedTextsError

# b /Users/mukund/Software/docInt/docint/pipeline/details_merger.py:34


@dataclass
class OfficerHistory:
    details: []
    officer_id: str
    names: set = field(default_factory=set)
    birth_dates: set = field(default_factory=set)

    def __post_init__(self):
        self.names.add(self.fix_name(self.details[0].officer.name))
        if self.details[0].officer.birth_date:
            self.birth_dates.add(self.details[0].officer.birth_date)

    @property
    def name(self):
        return self.details[0].officer.name

    @property
    def birth_date(self):
        return self.details[0].officer.birth_date

    def __len__(self):
        return len(self.details)

    def __str__(self):
        return f'[{len(self)}] {self.details[0].officer.cadre} {self.name}'

    def fix_name(self, name):
        return name.lower().replace(' ','')

    def get_last_post(self):
        posts = self.details[-1].get_after_posts()
        assert len(posts) in (0, 1)
        if posts and not posts[0].errors:
            return posts[0]
        else:
            return None

    def exact_name_date_match(self, d_name, d_birth_date):
        d_name = self.fix_name(d_name)
        for name, birth_date in product(self.names, self.birth_dates):
            if d_name == name and birth_date == d_birth_date:
                return True
        return False


    def fuzzy_name_date_match(self, d_name, d_birth_date, name_cutoff=2, date_cutoff=1):
        def leven_equal(d1, d2):
            return levenshtein(str(d1), str(d2), date_cutoff) <= date_cutoff

        def inv_equal(d1, d2):
            return d1.year == d2.year and d1.month == d1.day and d1.day == d2.month
        
        def fuzzy_date_match(d1, d2):
            return d1 == d2 or inv_equal(d1, d2) or leven_equal(d1, d2)

        d_name = self.fix_name(d_name)
        for name, birth_date in product(self.names, self.birth_dates):
            if levenshtein(d_name, name, name_cutoff) <= name_cutoff and fuzzy_date_match(d_birth_date, birth_date):
                return True
        return False

    def fuzzy_name_match(self, d_name, name_cutoff=2):
        d_name = self.fix_name(d_name)
        for name in self.names:
            if levenshtein(d_name, name, name_cutoff) <= name_cutoff:
                return True
        return False

    def add_detail(self, detail):
        self.names.add(self.fix_name(detail.officer.name))
        if detail.officer.birth_date:
            self.birth_dates.add(detail.officer.birth_date)
        self.details.append(detail)

@Vision.factory(
    "details_merger",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "details_merger",
        "pre_edit": True,
        "cadre_file_dict": {},
        "post_id_fields": [],
        "officer_match_fields": [],
    },
)
class DetailsMerger:
    def __init__(
        self,
        conf_dir,
        conf_stub,
        pre_edit,
        cadre_file_dict,
        post_id_fields,
        officer_match_fields,
    ):
        self.conf_dir = Path(conf_dir)
        self.conf_stub = Path(conf_stub)
        self.pre_edit = pre_edit
        self.post_id_fields = post_id_fields

        self.lgr = logging.getLogger(__name__)
        self.lgr.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(stream_handler)
        self.file_handler = None

    def add_log_handler(self, doc):
        handler_name = f"{doc.pdf_name}.{self.conf_stub}.log"
        log_path = Path("logs") / handler_name
        self.file_handler = logging.FileHandler(log_path, mode="w")
        self.lgr.info(f"adding handler {log_path}")

        self.file_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(self.file_handler)

    def remove_log_handler(self, doc):
        self.file_handler.flush()
        self.lgr.removeHandler(self.file_handler)
        self.file_handler = None

    def find_exact_matching_detail(self, officer_history, order, merged_details, o_idx):
        def get_valid_before_post(detail):
            posts = detail.get_before_posts()
            assert len(posts) in (0, 1)
            if posts and not posts[0].errors:
                return posts[0]
            else:
                return None

        
        o_id = officer_history.officer_id
        o_birth_date = officer_history.birth_date
        o_name = officer_history.name
        o_cadre = officer_history.details[0].officer.cadre
        o_last_post = officer_history.get_last_post()
        o_last_post_str = o_last_post.post_str if o_last_post else ""
        order_id = order.order_id

        for detail in order.details:
            if (order.order_id, detail.detail_idx) in merged_details:
                continue
            
            d_name, d_birth_date = detail.officer.name, detail.officer.birth_date
            
            if o_id:
                if o_id == detail.officer.officer_id:
                    self.lgr.info('\tFound: {order_id}:{o_idx} officer_id matched')                    
                    return detail
                else:
                    continue
                
            if o_cadre != detail.officer.cadre:
                continue

            #if o_name == d_name and o_birth_date == d_birth_date:
            if d_birth_date and officer_history.exact_name_date_match(d_name, d_birth_date):
                self.lgr.info('\tFound: {order_id}:{o_idx} name, date matched')                                    
                return detail

            before_post = get_valid_before_post(detail)
            before_post_str = before_post.post_str if before_post else ""
            if o_last_post and before_post and o_last_post.post_id == before_post.post_id:
                if d_birth_date and officer_history.fuzzy_name_date_match(d_name, d_birth_date, name_cutoff=2, date_cutoff=1):
                    self.lgr.info(f"\tPostMatched: {order_id}:{o_idx} {o_name}<->{d_name} {o_birth_date}<->{d_birth_date} |{o_last_post_str}<->{before_post_str}|")
                    return detail
                
                elif (d_birth_date is None) and officer_history.fuzzy_name_match(d_name, name_cutoff=2):
                    self.lgr.info(f"\tPostMatched-name: {order_id}:{o_idx} {o_name}<->{d_name} |{o_last_post_str}<->{before_post_str}|")
                    return detail
        return None

    def get_officer_histories(self, orders):
        def iter_details(orders):
            for o_idx, order in enumerate(orders):
                for detail in order.details:
                    yield o_idx, order, detail.detail_idx, detail

        orders = sorted(orders, key=attrgetter("date"))
        officer_histories, merged_details = [], set()

        for (o_idx, order, d_idx, detail) in iter_details(orders):
            if not detail.officer:
                self.lgr.info('\tSkipping: No officer')
                continue

            officer_id = detail.officer.officer_id            
            self.lgr.info(f'{order.order_id}:{o_idx}[{d_idx}] officer_id:{officer_id} name: {detail.officer.name} dob: {detail.officer.birth_date}')

            if (order.order_id, d_idx) in merged_details:
                self.lgr.info('\tSkipping: {order.order_id} merged {name: detail.officer.name}')
                continue

            merged_details.add((order.order_id, d_idx))
            o_history = OfficerHistory(details=[detail], officer_id=officer_id)
            
            # if o_history.birth_date is None:
            #     self.lgr.info('\tSkipping: no birth_date')                
            #     officer_histories.append(o_history)                
            #     continue

            child_oidx = o_idx
            for child_order in orders[o_idx + 1 :]:

                child_oidx += 1
                o_detail = self.find_exact_matching_detail(
                    o_history, child_order, merged_details, child_oidx
                )
                if o_detail:
                    o_history.add_detail(o_detail)
                    merged_details.add((child_order.order_id, o_detail.detail_idx))
                else:
                    #pass
                    self.lgr.info(f'\tNot Found: {child_order.order_id}:{child_oidx} officer_id: {officer_id}')
                    
            officer_histories.append(o_history)
        # end for
        return officer_histories

    def pipe(self, docs, **kwargs):
        def stats(nums):
            nums = list(nums)
            if not nums:
                return 'empty sequence'
            else:
                return f'min: {min(nums)} max: {max(nums)} avg: {mean(nums):.2f} median: {median(nums)}'

        
        self.lgr.info("Entering details_merger.pipe")

        orders = [doc.order for doc in docs]
        total_details = sum(len(o.details) for o in orders)
        noid_details = len([d for o in orders for d in o.details if d.officer.officer_id])
        
        officer_histories = self.get_officer_histories(orders)
        noid_officer_histories = [oh for oh in officer_histories if not oh.officer_id]

        print(f"#details: {total_details} #noid_details: {noid_details} #OHs: {len(officer_histories)} #noid_OHs: {len(noid_officer_histories)}")

        [self.lgr.info(oh) for oh in noid_officer_histories]

        
        print(f"stats: {stats(len(oh) for oh in noid_officer_histories)}")
        return docs
