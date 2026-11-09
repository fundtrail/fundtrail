"""The golden fixture: one hand-written synthetic grant every workstream tests against.

It follows the extension-notice example in docs/product.md. The story and its
expected buckets are described in docs/contracts.md.

    from app.contracts.fixtures import load_golden, load_golden_answer_key
"""

import json
from pathlib import Path

from ..base import Model
from ..charges import Charge
from ..eval import AnswerKey
from ..evidence import EvidenceFile
from ..records import Record
from ..workspaces import Grant, User, Workspace

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_DOCUMENTS = GOLDEN_DIR / "documents"  # originals, by EvidenceFile.name
GOLDEN_LEDGER = GOLDEN_DIR / "ledger.csv"


class GoldenFixture(Model):
    user: User
    workspace: Workspace
    grant: Grant
    charges: list[Charge]
    evidence: list[EvidenceFile]
    records: list[Record]  # in the order they were written


def load_golden() -> GoldenFixture:
    return GoldenFixture.model_validate(json.loads((GOLDEN_DIR / "fixture.json").read_text()))


def load_golden_answer_key() -> AnswerKey:
    return AnswerKey.model_validate(json.loads((GOLDEN_DIR / "answer_key.json").read_text()))
