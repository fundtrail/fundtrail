"""Extraction record: the contract between extraction and the rules engine.

Frozen core fields: doc_id, field, value, cited_text, block. The rest are
additions the rules engine may read but must not require.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Status = Literal[
    "verified",               # cited text states the same normalized value
    "not_found",              # model answered NOT FOUND
    "missing",                # model gave no line for this field
    "no_citation",            # value given, but nothing cited
    "value_not_in_citation",  # cited text does not state the value
]


class ExtractionRecord(BaseModel):
    doc_id: str
    field: str
    value: str | None              # exactly as the model wrote it
    cited_text: str | None
    block: int | None              # first cited block index
    block_end: int | None = None   # exclusive end of the cited block range
    kind: Literal["date", "money", "text"]
    value_normalized: str | int | None = None  # ISO date, cents, or normalized text
    status: Status

    @property
    def verified(self) -> bool:
        return self.status == "verified"
