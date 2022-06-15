import logging
import sys
import datetime
from dataclasses import dataclass
from operator import attrgetter
from itertools import groupby
from more_itertools import flatten
import json
from pathlib import Path

import yaml
from dateutil import parser

from ..vision import Vision
from ..extracts.orgpedia import Tenure


# b /Users/mukund/Software/docInt/docint/pipeline/id_assigner.py:34


# This should be called DetailPostInfo
@dataclass
class DetailInfo:
    order_id: str
    order_date: datetime.date
    detail_idx: int
    officer_id: str
    verb: str
    post_id: str
    order_category: str

    def __str__(self):
        return f'{self.order_id} {self.officer_id} {self.post_id}'


@Vision.factory(
    "tenure_builder",
    default_config={
        "conf_dir": "conf",
        "conf_stub": "tenure_builder",
        "ministry_file": "conf/ministries.yml",        
    },
)
class TenureBuilder:
    def __init__(self, conf_dir, conf_stub, ministry_file):
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub
        self.ministry_path = Path(ministry_file)

        if self.ministry_path.exists():
            self.ministry_dict = yaml.load(
                self.ministry_path.read_text(), Loader=yaml.FullLoader
            )
            for m in self.ministry_dict["ministries"]:
                s, e = m["start_date"], m["end_date"]
                m["start_date"] = parser.parse(s).date()
                m["end_date"] = (
                    parser.parse(e).date() if e != "today" else datetime.date.today()
                )
        else:
            self.ministry_dict = {}
        

        self.lgr = logging.getLogger(__name__)
        self.lgr.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.DEBUG)
        self.lgr.addHandler(stream_handler)
        self.file_handler = None
        self.curr_tenure_idx = 0

    def build_detail_infos(self, order):
        def valid_date(order):
            if not order.date:
                return False

            y = order.date.year
            return False if (y < 1947 or y > 2021) else True

        def iter_posts(detail):
            if not detail.officer.officer_id:
                return
            
            for verb in ["continues", "relinquishes", "assumes"]:
                for post in getattr(detail, verb):
                    yield verb, post

        def build_info(detail, verb, post):
            return DetailInfo(
                order.order_id,
                order.date,
                detail.detail_idx,
                detail.officer.officer_id,
                verb,
                post.post_id,
                order.category,
            )

        if not valid_date(order):
            return []

        return [build_info(d, v, p) for d in order.details for (v, p) in iter_posts(d)]

    def ministry_end_date(self, date):
        assert self.ministry_dict
        for m in self.ministry_dict["ministries"]:
            if m["start_date"] <= date < m["end_date"]:
                return m["end_date"]
        return None
    

    def build_officer_tenures(self, officer_id, detail_infos):
        def build_tenure(start_info, end_order_id, end_date, end_detail_idx):
            self.curr_tenure_idx += 1
            return Tenure(
                tenure_idx=self.curr_tenure_idx,
                officer_id=start_info.officer_id,
                post_id=start_info.post_id,
                start_date=start_info.order_date,
                end_date=end_date,
                start_order_id=start_info.order_id,
                start_detail_idx=start_info.detail_idx,
                end_order_id=end_order_id,
                end_detail_idx=end_detail_idx,
            )
        def get_postids(infos):
            infos = list(infos)
            if not infos:
                return '[0]'
            
            if isinstance(infos[0], DetailInfo):
                post_ids = [i.post_id for i in infos]
            else:
                post_ids = list(infos)
            return f'[{len(post_ids)}]: {", ".join(post_ids)}'


        def handle_order_infos(order_infos):
            first = order_infos[0]
            o_id, o_date, d_idx = first.order_id, first.order_date, first.detail_idx
            o_tenures = []
            active_posts = set(postid_info_dict.keys())
            self.lgr.info(f'\tActive{get_postids(active_posts)} Order{get_postids(order_infos)}')
            if first.order_category == "Council":
                order_posts = set(i.post_id for i in order_infos)
                ignored_posts = list(active_posts - order_posts)
                if ignored_posts:
                    for post_id in ignored_posts:
                        ignored_info = postid_info_dict[post_id]
                        o_tenures.append(build_tenure(ignored_info, o_id, o_date, d_idx))
                        del postid_info_dict[post_id]
                    self.lgr.info(f'\t\tClosing Actives*{get_postids(ignored_posts)}')                


            for info in order_infos:
                if info.verb in ("assumes", "continues"):
                    if info.post_id not in postid_info_dict:
                        postid_info_dict.setdefault(info.post_id, info)
                elif info.verb == "relinquishes":
                    start_info = postid_info_dict.get(info.post_id, None)
                    if not start_info:
                        self.lgr.warning(f"***Incorrect relinquish post_id: {info.post_id} not found in {str(info)}")
                        continue
                    o_tenures.append(build_tenure(start_info, o_id, o_date, d_idx))
                    self.lgr.info(f'\t\tClosing Active: {info.post_id}')
                    del postid_info_dict[info.post_id]
                else:
                    raise NotImplementedError(f"Unknown verb: {info.verb}")
            return o_tenures

        detail_infos = sorted(detail_infos, key=lambda i: (i.order_date, i.order_id))
        self.lgr.info(f'\n## Processing Officer: {officer_id} #detailpost_infos: {len(detail_infos)}')        

        postid_info_dict, officer_tenures = {}, []
        for order_id, order_infos in groupby(detail_infos, key=attrgetter("order_id")):
            order_infos = list(order_infos)
            self.lgr.info(f'Order: {order_id} #detailpost_infos: {len(order_infos)}')            
            officer_tenures += handle_order_infos(order_infos)

        if postid_info_dict:
            self.lgr.warning(f"***No Closing Orders{get_postids(postid_info_dict.keys())}")
            if self.ministry_dict:
                for post_id, info in postid_info_dict.items():
                    end_date = self.ministry_end_date(info.order_date)
                    officer_tenures.append(build_tenure(info, "", end_date, -1))
            
        return officer_tenures

    def write_tenures(self, tenures):
        tenure_dicts = []
        for t in tenures:
            td = t.dict()
            td['start_date'] = str(td['start_date'])
            td['end_date'] = str(td['end_date'])
            tenure_dicts.append(td)
        tenure_output_path = Path('output/tenures.json')
        tenure_output_path.write_text(json.dumps({'tenures': tenure_dicts}, indent=2))

    def pipe(self, docs, **kwargs):
        print("Inside tenure_builder")
        self.lgr.info("Entering tenure builder")
        docs = list(docs)        

        for doc in docs:
            doc.add_extra_field('tenures', ('list', 'docint.extracts.orgpedia', 'Tenure'))

        orders = [doc.order for doc in docs]
        detail_infos = list(flatten(self.build_detail_infos(o) for o in orders))

        detail_infos.sort(key=attrgetter("officer_id"))
        officer_groupby = groupby(detail_infos, key=attrgetter("officer_id"))

        tenures = []
        for officer_id, officer_infos in officer_groupby:
            tenures += self.build_officer_tenures(officer_id, officer_infos)

        self.lgr.info(f"#Tenures: {len(tenures)}")
        order_id_doc_dict = {}
        for doc in docs:
            order_id_doc_dict[doc.order.order_id] = doc
            doc.tenures = []

            
        for tenure in tenures:
            doc = order_id_doc_dict[tenure.start_order_id]
            doc.tenures.append(tenure)

        self.write_tenures(tenures)

        self.lgr.info("Leaving tenure_builder")
        return docs
