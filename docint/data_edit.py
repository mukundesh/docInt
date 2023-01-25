from typing import List

from pydantic import BaseModel


class DataEdit(BaseModel):
    cmd: str
    paths: List[str]

    def __str__(self):
        return f"{self.cmd} [{len(self.paths)}] {str(self.paths)}"
