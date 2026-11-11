"""A file uploaded as a new grant's award letter that isn't one gets the agent's flag (#278).

QA added a grant from `lunch_order.txt`. The agent saw it wasn't an award letter, said so in its
run summary, and saved nothing, so no screen said anything. Now the run reading a new grant's
award letter can't end until the agent has written a term from it or flagged the file, and the
flag is a problem on that file in the checks' own words, like any other problem.

No model is called: a fake model first tries to finish, then flags.
"""

from dataclasses import replace
from datetime import datetime
from typing import Any

from app.agent import RunSaved, run_once
from app.agent.citations import LabelLine
from app.agent.context import RunContext
from app.agent.desk import AWARD_LETTER_NOTE, award_letter_file, award_letter_unread
from app.agent.model import ModelRequest
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.checks.run import run_checks
from app.contracts.checks import ChecksInput
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import Judgment, Question
from app.contracts.runs import Trigger, TriggerKind

from .fakes import FakeModel, calls, message, results_of, sample_inputs, text, tool
from .test_sample_email_dates import _cite

SAMPLE = load_sample_grant()
LUNCH = b"Lunch order for Friday: two sandwiches, one salad.\n"
ADDED = datetime.fromisoformat("2023-01-12T15:00:00+00:00")
LUNCH_FILE = SAMPLE.files[0].model_copy(
    update={
        "id": "file-lunch-order",
        "name": "lunch_order.txt",
        "storage_path": "ws-sample/grant-sample/file-lunch-order/lunch_order.txt",
        "arrived_at": ADDED,
    }
)
QUESTION = (
    "This file is a lunch order, not an award notice, so no terms could be read from it. "
    "Upload the grant's award letter."
)


def new_grant_inputs(**changes: Any):
    base = sample_inputs(
        now=ADDED, trigger=Trigger(kind=TriggerKind.FILE, id=LUNCH_FILE.id), records=[]
    )
    return replace(base, files=[LUNCH_FILE], read_file=lambda f: LUNCH, charges=[], **changes)


def flag_the_file(request: ModelRequest):
    return calls(
        tool(
            "flag",
            file_id=LUNCH_FILE.id,
            question=QUESTION,
            reasoning="It lists two sandwiches and one salad for Friday; it has no award terms.",
        )
    )


def test_the_run_cant_end_until_the_file_is_flagged_and_the_flag_is_a_problem_on_it():
    model = FakeModel(
        [
            lambda r: message(text("This is a lunch order, so there's nothing to save.")),
            flag_the_file,
            lambda r: message(text("Done.")),
        ]
    )
    result = run_once(new_grant_inputs(), model)
    assert isinstance(result, RunSaved), result

    # The first message says the file came in as the award letter.
    first = model.requests[0].messages[0]["content"]
    assert AWARD_LETTER_NOTE in " ".join(b.get("text", "") for b in first)
    # Trying to finish without a term or a flag sends the model back, saying why.
    sent_back = model.requests[1].messages[-1]["content"]
    said = (
        sent_back
        if isinstance(sent_back, str)
        else " ".join(b.get("text", "") or str(b.get("content", "")) for b in sent_back)
    )
    assert "uploaded as the grant's award letter" in said and LUNCH_FILE.id in said
    assert not any(r.get("is_error") for r in results_of(model.requests[2]))

    [flag] = result.records
    assert isinstance(flag.data, Judgment) and flag.data.question == Question.FLAG
    assert flag.data.file_id == LUNCH_FILE.id and flag.data.charge_id is None

    # The checks raise the flag as a problem on the file, in their own words.
    out = run_checks(
        ChecksInput(now=ADDED, charges=(), files=(LUNCH_FILE,), records=tuple(result.records))
    )
    [status] = [s for s in out.records if s.file_id == LUNCH_FILE.id]
    assert [p.text for p in status.problems] == [f"The agent flagged this: {QUESTION}"]


def test_a_term_from_the_award_letter_lets_the_run_end_with_no_flag():
    """An award letter the agent reads as one needs no flag: a term citing it is enough."""
    letter = SAMPLE.files[0]  # the sample's award letter, as a new grant's first file
    inputs = replace(
        sample_inputs(now=ADDED, trigger=Trigger(kind=TriggerKind.FILE, id=letter.id), records=[]),
        files=[letter],
        charges=[],
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    assert award_letter_unread(ctx) == letter
    result, error = run_tool(ctx, "open_file", {"file_id": letter.id})
    assert not error, result
    award = SAMPLE.document(letter.id)
    for name, value, chunk in [
        ("dated", "January 10, 2023", "Amendment Date: January 10, 2023"),
        ("start", "February 1, 2023", "Period of Performance Start Date: February 1, 2023"),
        ("end", "January 31, 2026", "Period of Performance End Date: January 31, 2026"),
    ]:
        ctx.labels[name] = LabelLine(name, value, [_cite(award, chunk)])
    values = [
        {"field": "dated", "label": "dated", "value": "2023-01-10"},
        {"field": "start", "label": "start", "value": "2023-02-01"},
        {"field": "end", "label": "end", "value": "2026-01-31"},
    ]
    result, error = run_tool(ctx, "write_term", {"kind": "period_of_performance", "values": values})
    assert not error, result
    assert award_letter_unread(ctx) is None


def test_only_a_new_grants_first_file_is_treated_as_its_award_letter():
    assert award_letter_file(RunContext(new_grant_inputs(), load_rulebook())) is not None
    # A grant that already has terms: an ordinary file run.
    later = sample_inputs(
        now=datetime.fromisoformat("2025-11-14T00:00:00+00:00"),
        trigger=Trigger(kind=TriggerKind.FILE, id="file-invoice-1001"),
        records=[r for r in SAMPLE.records if r.kind.value == "period_of_performance"],
    )
    assert award_letter_file(RunContext(later, load_rulebook())) is None
    # A file that isn't the grant's first.
    second = replace(
        new_grant_inputs(),
        files=[
            SAMPLE.files[0],
            LUNCH_FILE.model_copy(update={"arrived_at": ADDED.replace(day=13)}),
        ],
    )
    assert award_letter_file(RunContext(second, load_rulebook())) is None
