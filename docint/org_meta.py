from typing import List

from pydantic import BaseModel


class OrgMeta(BaseModel):
    is_text: bool
    language: str
    page_languages: List[str] = []
    cadre: str
    order_type: str
    website: str = ""
    # is_multi_order: bool = False
