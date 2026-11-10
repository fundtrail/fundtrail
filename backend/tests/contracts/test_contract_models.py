"""The models follow docs/contracts.md's conventions and record rules."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.contracts import api
from app.contracts.charges import Charge, LedgerRow
from app.contracts.checks import (
    Bucket,
    ChargeStatus,
    ChecklistEntry,
    ChecksInput,
    ItemSource,
    Reason,
    run_checks,
)
from app.contracts.records import (
    BudgetCategory,
    Citation,
    Judgment,
    Record,
    categories_match,
    cited_values,
)
from app.contracts.runs import Trigger, TriggerKind
from app.contracts.threads import ThreadMessage
from tests.contracts.factory import CHARGE, answer, at, bill, citation, cited, link, sign_off, user


def record(**changes: Any) -> Record:
    fields: dict[str, Any] = {
        "id": "r1",
        "workspace_id": "w",
        "grant_id": "g",
        "author": "user",
        "author_user_id": "u",
        "written_at": at(0),
        "data": sign_off(),
    }
    return Record.model_validate(fields | changes)


def agent_record(**changes: Any) -> Record:
    return record(**({"author": "agent", "author_user_id": None} | changes))


def test_models_are_frozen_and_reject_unknown_fields():
    with pytest.raises(ValidationError):
        record().id = "r2"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        record(color="blue")
    with pytest.raises(ValidationError):
        record(data=sign_off() | {"color": "blue"})


def test_money_is_integer_cents():
    with pytest.raises(ValidationError):
        CHARGE.model_validate(CHARGE.model_dump() | {"amount_cents": 12.5})
    with pytest.raises(ValidationError):
        CHARGE.model_validate(CHARGE.model_dump() | {"amount_cents": "1200"})


def test_timestamps_are_aware_and_stored_in_utc():
    pacific = datetime(2026, 2, 21, 9, 30, tzinfo=timezone(timedelta(hours=-8)))
    r = record(written_at=pacific)
    assert r.written_at.tzinfo == UTC and r.written_at.hour == 17
    with pytest.raises(ValidationError):
        record(written_at=datetime(2026, 2, 21, 9, 30))


def test_record_rules():
    uncited = {
        "kind": "period_of_performance",
        "dated": {"value": "2023-01-10"},
        "end": {"value": "2026-01-31"},
    }
    record(data=uncited)  # the accountant enters a value with no citation
    flag = answer("supports", question="flag", text="Odd?")
    for bad in (
        {"author_user_id": None},  # the accountant's record names them
        {"replaces_id": "r1"},  # a record can't replace itself
        {"data": {"kind": "retraction"}},  # a retraction names what it replaces
    ):
        with pytest.raises(ValidationError):
            record(**bad)
    for bad in (
        {"data": sign_off()},  # only the accountant signs off
        {"data": {"kind": "confirmation", "record_ids": ["x"]}},
        {
            "data": {
                "kind": "snooze",
                "until": "2026-03-01",
                "note": "n",
                "reasons": [{"check": "c", "problem": "p"}],
            }
        },
        {"data": uncited},  # the agent always cites
        {"data": link(part=None)},  # the agent's link has a part
        {"data": flag},  # the agent's flag is unsure
        {"author_user_id": "u", "data": bill()},  # only the accountant's record names a user
    ):
        with pytest.raises(ValidationError):
            agent_record(**bad)
    agent_record(data=flag | {"answer": "unsure"})
    record(data=flag)  # the accountant settles a flag by answering it


def test_nested_values_need_citations_too():
    item = {"description": {"value": "x"}, "amount": {"value": 100}}
    with pytest.raises(ValidationError):
        agent_record(data=bill() | {"items": [item]})
    paths = [
        p
        for p, _ in cited_values(
            agent_record(
                data=bill() | {"items": [{"description": cited("x", "x"), "amount": cited(1, "1")}]}
            ).data
        )
    ]
    assert paths == ["total", "items[0].description", "items[0].amount"]


def test_citation_rules():
    box = {"type": "image_box", "page": 1, "left": 0.1, "top": 0.2, "width": 0.3, "height": 0.1}
    Citation.model_validate({"file_id": "f", "passage": None, "location": box, "match": "exact"})
    pages = {"type": "page_location", "start_page_number": 1, "end_page_number": 2}
    highlight = [{"page": 1, "left": 0.1, "top": 0.1, "width": 0.5, "height": 0.02}]
    Citation.model_validate(
        {"file_id": "f", "passage": "p", "location": pages, "highlight": highlight}
    )
    for bad in (
        {"file_id": "f", "passage": "typed by the model", "location": box},
        {"file_id": "f", "passage": None, "location": pages},
        {
            "file_id": "f",
            "passage": "p",
            "location": citation()["location"],
            "highlight": highlight,
        },
        {"file_id": "f", "passage": None, "location": box | {"left": 0.9}},  # off the page
        {
            "file_id": "f",
            "passage": "p",
            "location": {"type": "char_location", "start_char_index": 5, "end_char_index": 5},
        },
    ):
        with pytest.raises(ValidationError):
            Citation.model_validate(bad)


def test_a_cited_value_has_its_text():
    with pytest.raises(ValidationError):
        record(data=bill() | {"total": {"value": 1200, "citation": citation()}})


def test_judgment_subjects():
    Judgment.model_validate(answer("supports"))
    Judgment.model_validate(answer("unsure", question="flag", charge_id=None, file_id="f1"))
    for bad in (
        answer("supports", charge_id=None),  # allowable is about a charge
        answer("supports", record_id="x"),  # and not about a record
        answer("supports", question="covers"),  # covers names its approval
        answer("unsure", question="flag", charge_id=None),  # a flag is about something
    ):
        with pytest.raises(ValidationError):
            Judgment.model_validate(bad)


def test_checklist_shapes():
    rate_item = {
        "kind": "checklist_item",
        "charge_id": "c1",
        "needed": "Per diem, 5 days at $100 a day",
        "amount_cents": 50000,
        "rate": {"quantity": cited(Decimal(5), "5 days"), "rate": cited(Decimal(10000), "$100")},
    }
    record(data=rate_item)
    with pytest.raises(ValidationError):
        record(data=rate_item | {"amount_cents": None})
    with pytest.raises(ValidationError):  # the rate is cited or a term, not both
        record(data=rate_item | {"rate": rate_item["rate"] | {"rate_id": "t1"}})
    with pytest.raises(ValidationError):
        record(data={"kind": "checklist_removal", "charge_id": "c1"})
    with pytest.raises(ValidationError):
        record(data=link(item_record_id="i1"))  # a link fills at most one item


def test_accepted_reasons_and_snoozes_are_about_at_most_one_thing():
    reason = {"check": "budget", "problem": "over_limit"}
    record(data={"kind": "accepted_reason", "reason": reason, "note": "Known."})  # the grant itself
    with pytest.raises(ValidationError):
        record(
            data={
                "kind": "accepted_reason",
                "reason": reason,
                "note": "n",
                "charge_id": "c",
                "file_id": "f",
            }
        )


def test_budget_categories():
    assert categories_match(
        BudgetCategory.MATERIALS_AND_SUPPLIES, BudgetCategory.OTHER_DIRECT_COSTS
    )
    assert categories_match(
        BudgetCategory.OTHER_DIRECT_COSTS, BudgetCategory.OTHER_DIRECT_COSTS_OTHER
    )
    assert categories_match(BudgetCategory.TRAVEL, BudgetCategory.TRAVEL)
    assert not categories_match(
        BudgetCategory.MATERIALS_AND_SUPPLIES, BudgetCategory.OTHER_DIRECT_COSTS_OTHER
    )
    assert not categories_match(
        BudgetCategory.PARTICIPANT_SUPPORT, BudgetCategory.OTHER_DIRECT_COSTS
    )


def test_ledger_row_becomes_a_charge():
    row = LedgerRow(
        line_id="L-9",
        transaction_date=date(2026, 1, 2),
        posting_date=date(2026, 1, 4),
        amount=Decimal("-1240.00"),
        description="Credit",
        account="55016 Lab Instruments and Supplies",
    )
    # Decision 0023: uploaded before its posting date, it arrives at that date's midnight.
    early = datetime(2026, 1, 1, 9, tzinfo=UTC)
    c = row.to_charge(id="c9", workspace_id="w", grant_id="g", now=early)
    assert c.amount_cents == -124000 and c.ledger_line_id == "L-9"
    assert c.arrived_at == datetime(2026, 1, 4, tzinfo=UTC)
    # Uploaded on or after its posting date, it arrives now.
    late = datetime(2026, 2, 1, 9, 30, tzinfo=timezone(timedelta(hours=-8)))
    assert row.to_charge(id="c9", workspace_id="w", grant_id="g", now=late).arrived_at == late
    on_the_day = datetime(2026, 1, 4, tzinfo=UTC)
    assert row.arrival(on_the_day) == on_the_day
    with pytest.raises(ValidationError):
        LedgerRow.model_validate(row.model_dump() | {"amount": Decimal("1.234")})


def test_a_charges_bucket_is_its_most_serious_reason():
    reasons = [
        Reason(check="checklist", problem="missing", bucket=Bucket.MISSING_EVIDENCE, text="x"),
        Reason(
            check="period_of_performance",
            problem="after_end_date",
            bucket=Bucket.POSSIBLE_CONFLICT,
            text="y",
        ),
    ]
    ChargeStatus(
        grant_id="g",
        charge_id="c",
        bucket=Bucket.POSSIBLE_CONFLICT,
        reasons=tuple(reasons),
        checklist=(),
        flagged=True,
    )
    with pytest.raises(ValidationError):
        ChargeStatus(
            grant_id="g",
            charge_id="c",
            bucket=Bucket.MISSING_EVIDENCE,
            reasons=tuple(reasons),
            checklist=(),
            flagged=True,
        )


def test_checklist_entries_name_one_item():
    ChecklistEntry(default_item="bill", added_by=ItemSource.DEFAULT, needed="A bill", filled=True)
    with pytest.raises(ValidationError):
        ChecklistEntry(default_item="bill", added_by=ItemSource.AGENT, needed="A bill", filled=True)
    with pytest.raises(ValidationError):
        ChecklistEntry(added_by=ItemSource.AGENT, needed="A bill", filled=True)


def test_triggers_name_what_changed_except_the_clock():
    Trigger(kind=TriggerKind.CLOCK)
    Trigger(kind=TriggerKind.THREAD_MESSAGE, id="m1")
    with pytest.raises(ValidationError):
        Trigger(kind=TriggerKind.RECORD)
    with pytest.raises(ValidationError):
        Trigger(kind=TriggerKind.CLOCK, id="x")


def test_thread_message_rules():
    base: dict[str, Any] = {
        "id": "m",
        "workspace_id": "w",
        "grant_id": "g",
        "text": "Why?",
        "written_at": at(0),
    }
    ThreadMessage.model_validate(base | {"charge_id": "c", "author": "user", "author_user_id": "u"})
    ThreadMessage.model_validate(base | {"record_id": "r", "author": "agent", "run_id": "run1"})
    for bad in (
        {"author": "user", "author_user_id": "u"},  # about nothing
        {"charge_id": "c", "record_id": "r", "author": "user", "author_user_id": "u"},
        {"charge_id": "c", "author": "agent"},  # the agent's message names its run
        {"charge_id": "c", "author": "user", "author_user_id": "u", "run_id": "run1"},
    ):
        with pytest.raises(ValidationError):
            ThreadMessage.model_validate(base | bad)


def test_run_checks_is_declared_for_w2():
    with pytest.raises(NotImplementedError):
        run_checks(
            ChecksInput(now=at(0), charges=(CHARGE,), files=(), records=(user("b", bill()),))
        )


def test_api_bodies_have_json_schemas():
    models = [
        m
        for m in vars(api).values()
        if isinstance(m, type) and issubclass(m, BaseModel) and m.__module__ == api.__name__
    ]
    assert len(models) >= 9
    for m in models:
        m.model_json_schema()
    api.NewRecordInput.model_validate({"data": bill()})


def test_charge_round_trips_through_json():
    assert Charge.model_validate_json(CHARGE.model_dump_json()) == CHARGE


def test_an_item_an_approval_rule_added_names_the_rule():
    """Issue 115: not "Account default"."""
    entry = ChecklistEntry(
        default_item="approval:t1",
        added_by=ItemSource.RULE,
        rule_id="t1",
        needed="The Program Officer's approval through Research.gov",
        filled=False,
    )
    assert entry.added_by == "rule" and entry.rule_id == "t1"
    with pytest.raises(ValidationError):  # a rule's item names its rule
        ChecklistEntry(
            default_item="approval:t1", added_by=ItemSource.RULE, needed="x", filled=False
        )
    with pytest.raises(ValidationError):  # only a rule's item names one
        ChecklistEntry(
            default_item="bill", added_by=ItemSource.DEFAULT, rule_id="t1", needed="x", filled=False
        )
    with pytest.raises(ValidationError):  # a rule's item isn't stored
        ChecklistEntry(
            item_record_id="i1", added_by=ItemSource.RULE, rule_id="t1", needed="x", filled=False
        )
