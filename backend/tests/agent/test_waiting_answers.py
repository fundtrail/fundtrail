"""A run whose new answer waits for the accountant can finish (issue #136).

In the second end-to-end run the agent had answered L-1002's Allowable "contradicts". A receipt
arrived, the agent linked a note from it and answered supports, which waits for the accountant
by design (contradicts turning milder always waits). The checks kept listing the question as
open for the agent, the gate sent it back three times, and the run failed, losing everything.
"""

from dataclasses import replace
from datetime import datetime

import pytest

from app.agent import RunSaved, run_once
from app.agent.model import ModelRequest
from app.checks.checklist import default_items
from app.checks.run import run_checks
from app.contracts.evidence import EvidenceFile
from app.contracts.fixtures import DOCUMENTS_DIR, load_sample_grant
from app.contracts.records import Answer, Judgment, Link, Note, Record
from app.contracts.rules import RecordState
from app.contracts.runs import Trigger, TriggerKind

from .fakes import FakeModel, calls, label_message, results_of, sample_inputs, tool

SAMPLE = load_sample_grant()
NOW = datetime.fromisoformat("2026-03-01T12:00:00+00:00")
RECEIPT = (
    "SYNTHETIC DEMO DOCUMENT. Created for the FundTrail sample grant.\n\n"
    "Example Sequencing Core\n"
    "Sample submission receipt for work order SEQ-0207, received January 22, 2026.\n"
)


def records_with(answer: str) -> list[Record]:
    """The sample up to L-1002's link and budget line, then the agent's Allowable `answer`."""
    out: list[Record] = []
    for r in SAMPLE.records:
        if r.id == "rec-allowable-l-1002":
            data = r.data.model_copy(update={"answer": Answer(answer)})
            out.append(r.model_copy(update={"data": data}))
            break
        out.append(r)
    return out


def receipt_run(earlier: str, new_answer: str) -> tuple[RunSaved, list[Record], list[EvidenceFile]]:
    receipt = SAMPLE.files[1].model_copy(
        update={
            "id": "file-receipt",
            "name": "receipt_seq_0207.txt",
            "storage_path": f"{SAMPLE.workspace.id}/{SAMPLE.grant.id}/file-receipt/"
            "receipt_seq_0207.txt",
            "sha256": "receipt",
            "arrived_at": datetime.fromisoformat("2026-03-01T11:00:00+00:00"),
        }
    )
    db = records_with(earlier)
    base = sample_inputs(
        now=NOW, trigger=Trigger(kind=TriggerKind.FILE, id="file-receipt"), records=db
    )
    inputs = replace(
        base,
        files=[*base.files, receipt],
        read_file=lambda f: (
            RECEIPT.encode() if f.id == "file-receipt" else (DOCUMENTS_DIR / f.name).read_bytes()
        ),
        run_checks=run_checks,
        default_items=default_items,
    )
    line = "Sample submission receipt for work order SEQ-0207, received January 22, 2026."

    def read(request: ModelRequest):
        return label_message(request, [("receipt", line, "file-receipt", line)])

    def write(request: ModelRequest):
        return calls(
            tool(
                "write_fact",
                kind="note",
                label="Sample submission receipt",
                values=[{"field": "statement", "label": "receipt"}],
            ),
            tool(
                "link",
                record_id="rec-new-1",
                charge_id="chg-l-1002",
                reason="The receipt for work order SEQ-0207.",
            ),
            tool(
                "answer",
                charge_id="chg-l-1002",
                question="allowable",
                answer=new_answer,
                reasoning="Sequencing run 7 for the survey's samples, at the core's usual price.",
                rests_on=["rec-bill-seq-0207"],
            ),
            tool("finish", summary="Read the receipt and answered again."),
        )

    def unexpected(request: ModelRequest):
        pytest.fail(f"the gate sent the run back: {results_of(request)[-1]['content']}")

    result = run_once(inputs, FakeModel([read, write, unexpected]))
    assert isinstance(result, RunSaved), getattr(result, "error", result)
    return result, db, list(inputs.files)


@pytest.mark.parametrize("earlier", ["contradicts", "unsure"])
def test_a_new_answer_that_waits_lets_the_run_finish_and_nothing_is_lost(earlier: str):
    """Contradicts turning into supports always waits; unsure turning into supports waits unless
    the contract counts new evidence. Either way the run saves everything it wrote."""
    result, db, files = receipt_run(earlier, "supports")
    kinds = [type(r.data) for r in result.records]
    assert kinds == [Note, Link, Judgment]
    state = RecordState([*db, *result.records], files)
    answer = result.records[-1]
    assert state.is_waiting(answer.id) or state.is_current(answer.id)
    if earlier == "contradicts":
        assert state.is_waiting(answer.id)
    assert state.is_current(result.records[1].id)  # the link to the receipt's note counts


def test_the_question_stays_the_agents_while_it_has_no_fresh_answer():
    """Without an answer after the new link, the gate still sends the run back."""
    from app.agent.adapter import agent_has_answered
    from app.contracts.checks import ChecksInput

    result, db, files = receipt_run("contradicts", "supports")
    without_answer = [*db, *result.records[:2]]
    out = run_checks(
        ChecksInput(
            now=NOW,
            charges=tuple(SAMPLE.charges),
            files=tuple(files),
            records=tuple(without_answer),
        )
    )
    question = next(q for q in out.questions if q.charge_id == "chg-l-1002")
    assert not agent_has_answered(question, without_answer, SAMPLE.charges, files, SAMPLE.grant.id)
    with_answer = [*db, *result.records]
    assert agent_has_answered(question, with_answer, SAMPLE.charges, files, SAMPLE.grant.id)
