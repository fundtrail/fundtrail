"""The sample grant: one small synthetic grant every area tests against.

It's described in docs/contracts.md section 15.

    from app.contracts.fixtures import load_sample_grant, load_sample_answer_key

The documents are in golden/documents/, the ledger file is golden/ledger.csv,
and the records, charges and files are golden/sample_grant.json, written by
build_sample.py. Everything in it is synthetic.
"""

import json
from collections.abc import Sequence
from functools import cache
from pathlib import Path

from ..base import Model
from ..charges import Charge
from ..eval import AnswerKey
from ..evidence import EvidenceFile
from ..records import DefaultItem, Record
from ..workspaces import Grant, User, Workspace

GOLDEN_DIR = Path(__file__).parent / "golden"
DOCUMENTS_DIR = GOLDEN_DIR / "documents"  # the originals, by EvidenceFile.name
LEDGER_FILE = GOLDEN_DIR / "ledger.csv"
SAMPLE_GRANT_FILE = GOLDEN_DIR / "sample_grant.json"
ANSWER_KEY_FILE = GOLDEN_DIR / "answer_key.json"


class SampleGrant(Model):
    user: User  # the accountant
    workspace: Workspace
    grant: Grant
    charges: list[Charge]
    files: list[EvidenceFile]
    records: list[Record]  # in the order they were written
    # Each charge's default checklist items, by ledger line ID: a stand-in for
    # the checks' table of account groups (W2), as section 15 gives them.
    default_items: dict[str, list[DefaultItem]]

    def document(self, file_id: str) -> str:
        """The text of one of the sample's files."""
        name = next(f.name for f in self.files if f.id == file_id)
        return (DOCUMENTS_DIR / name).read_text(encoding="utf-8")

    def sample_default_items(self, charge: Charge, records: Sequence[Record]) -> list[DefaultItem]:
        """Matches rules.DefaultItems, for passing to check_new_record."""
        return self.default_items.get(charge.ledger_line_id, [])


@cache
def load_sample_grant() -> SampleGrant:
    return SampleGrant.model_validate_json(SAMPLE_GRANT_FILE.read_text(encoding="utf-8"))


@cache
def load_sample_answer_key() -> AnswerKey:
    return AnswerKey.model_validate(json.loads(ANSWER_KEY_FILE.read_text(encoding="utf-8")))
