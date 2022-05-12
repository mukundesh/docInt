import logging
import sys
import datetime
from dataclasses import dataclass
from operator import attrgetter
from itertools import groupby
from more_itertools import flatten

from ..vision import Vision
from ..extracts.orgpedia import Tenure


# b /Users/mukund/Software/docInt/docint/pipeline/id_assigner.py:34


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
    },
)
class TenureBuilder:
    def __init__(self, conf_dir, conf_stub):
        self.conf_dir = conf_dir
        self.conf_stub = conf_stub

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

        def handle_order_infos(order_infos):
            first = order_infos[0]
            o_id, o_date, d_idx = first.order_id, first.order_date, first.detail_idx

            o_tenures = []
            active_posts = set(postid_info_dict.keys())
            if first.order_category == "Council":
                order_posts = set(i.post_id for i in order_infos)
                ignored_posts = active_posts - order_posts
                if ignored_posts:
                    i_infos = [postid_info_dict[p_id] for p_id in ignored_posts]
                    o_tenures.extend(
                        [build_tenure(i, o_id, o_date, d_idx) for i in i_infos]
                    )

            for info in order_infos:
                if info.verb in ("assumes", "continues"):
                    postid_info_dict.setdefault(info.post_id, info)
                else:
                    start_info = postid_info_dict.get(info.post_id, None)
                    if not start_info:
                        self.lgr.warning(f"Incorrect relinquish {str(info)}")
                        continue
                    o_tenures.append(build_tenure(start_info, o_id, o_date, d_idx))
                    del postid_info_dict[info.post_id]
            return o_tenures

        detail_infos = sorted(detail_infos, key=lambda i: (i.order_date, i.order_id))

        postid_info_dict, officer_tenures = {}, []
        for order_id, order_infos in groupby(detail_infos, key=attrgetter("order_id")):
            officer_tenures += handle_order_infos(list(order_infos))
        return officer_tenures

    def pipe(self, docs, **kwargs):
        self.lgr.info("Entering infer_layoutlm.pipe")

        orders = [doc.order for doc in docs]
        detail_infos = list(flatten(self.build_detail_infos(o) for o in orders))

        detail_infos.sort(key=attrgetter("officer_id"))
        officer_groupby = groupby(detail_infos, key=attrgetter("officer_id"))

        tenures = []
        for officer_id, officer_infos in officer_groupby:
            tenures += self.build_officer_tenures(officer_id, officer_infos)

        self.lgr.info("Leaving infer_layoutlm.pipe")
        return docs
