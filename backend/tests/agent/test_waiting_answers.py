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


def receipt_run(
    earlier: str, new_answer: str, *, stored: bool = False, receipt_seq: int = 1000
) -> tuple[RunSaved, list[Record], list[EvidenceFile]]:
    """The receipt run. With `stored`, every file and record carries its stored order, as the
    database gives them, the earlier answer carries the read point of the run that wrote it
    (everything stored before it), and this run reads through 1000. The receipt is stored at
    `receipt_seq`: at the read point the run read it; above it, it was stored during the run."""
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
    files = [*base.files, receipt]
    read_through = base.read_through_seq
    if stored:
        # Files first (each arrived before the records read from it), then the records in the
        # order written. The earlier answer is last: its run read everything stored before it.
        files = [f.model_copy(update={"stored_seq": i + 1}) for i, f in enumerate(base.files)]
        db = [r.model_copy(update={"stored_seq": 100 + i}) for i, r in enumerate(db)]
        earlier_answer = db[-1]
        assert isinstance(earlier_answer.data, Judgment)
        db[-1] = earlier_answer.model_copy(
            update={"read_through_seq": (earlier_answer.stored_seq or 0) - 1}
        )
        read_through = 1000
        files.append(receipt.model_copy(update={"stored_seq": receipt_seq}))
    inputs = replace(
        base,
        records=db,
        read_through_seq=read_through,
        files=files,
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


def test_with_stored_orders_a_receipt_read_by_the_run_lets_supports_take_effect():
    """PR 139's review: the receipt is stored before the run's read point, so it's new evidence
    for the run's answer, and unsure turning into supports takes effect at once."""
    result, db, files = receipt_run("unsure", "supports", stored=True)
    answer = result.records[-1]
    assert answer.read_through_seq == 1000
    state = RecordState([*db, *result.records], files)
    assert state.is_current(answer.id) and not state.is_waiting(answer.id)


def test_with_stored_orders_a_receipt_stored_during_the_run_isnt_new_evidence():
    """The control: stored above the run's read point, the receipt wasn't read by the run, so
    nothing new arrived for the answer and unsure turning into supports waits. If the receipt
    stopped counting as new evidence, the test above would fail; if anything else counted, this
    one would."""
    result, db, files = receipt_run("unsure", "supports", stored=True, receipt_seq=2000)
    state = RecordState([*db, *result.records], files)
    answer = result.records[-1]
    assert state.is_waiting(answer.id) and not state.is_current(answer.id)


def test_the_receipt_is_the_only_new_evidence_for_the_answer():
    """Asked of the contract directly: new evidence with the receipt read by the run, none
    without it."""
    result, db, files = receipt_run("unsure", "supports", stored=True)
    earlier, answer = db[-1], result.records[-1]
    with_receipt = RecordState([*db, *result.records], files)
    assert with_receipt.new_evidence_since(earlier, answer)
    without_receipt = RecordState(
        [*db, *result.records], [f for f in files if f.id != "file-receipt"]
    )
    assert not without_receipt.new_evidence_since(earlier, answer)


def test_with_stored_orders_contradicts_turning_into_supports_still_waits():
    result, db, files = receipt_run("contradicts", "supports", stored=True)
    state = RecordState([*db, *result.records], files)
    assert state.is_waiting(result.records[-1].id)
