"""The second contract change (issue 39): screen bodies and decisions 0020 to 0026."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.contracts import api
from app.contracts.buckets import Bucket
from app.contracts.checks import (
    ChargeStatus,
    ChecksInput,
    Reason,
    ready_for_closeout,
    snapshot_of,
)
from app.contracts.corrections import net_amounts
from app.contracts.eval import AnswerKey
from app.contracts.evidence import EvidenceFile
from app.contracts.fixtures import load_sample_answer_key
from app.contracts.mail import CheckerProgress, HeldMail, SkippedFile
from app.contracts.records import Citation, Record
from app.contracts.rules import RecordState, check_new_record, still_held, waiting_records
from app.contracts.runs import (
    CHARGE_BATCH,
    AgentRun,
    Trigger,
    TriggerKind,
    batch_for,
    charge_batches,
)
from app.contracts.signoff import ChangeKind, SignOffStateName, changes_since, sign_off_state
from app.contracts.workspaces import Grant
from tests.contracts.factory import (
    CHARGE,
    CHARGES,
    FILES,
    agent,
    answer,
    at,
    bill,
    budget_line,
    cited,
    confirm,
    defaults,
    file,
    ids,
    link,
    problems,
    sign_off,
    user,
)


def charge(
    line: str, cents: int, *, original: str | None = None, grant: str = "g", hours: float = 0
):
    return CHARGE.model_copy(
        update={
            "id": f"c-{line}",
            "ledger_line_id": line,
            "amount_cents": cents,
            "original_line_id": original,
            "grant_id": grant,
            "arrived_at": at(hours),
        }
    )


# Ruling 1: what a charge-triggered run covers.


def test_a_run_covers_the_charges_that_arrived_with_its_trigger_in_batches():
    together = [charge(f"L-{n:03}", 100) for n in range(CHARGE_BATCH + 5)]
    later = charge("L-900", 100, hours=1)
    elsewhere = charge("L-901", 100, grant="other")
    everything = [*reversed(together), later, elsewhere]
    batches = charge_batches(everything)
    assert [len(b) for b in batches] == [CHARGE_BATCH, 5, 1, 1]
    assert [c.ledger_line_id for c in batches[0]][:2] == ["L-000", "L-001"]  # line ID order

    first = batch_for("c-L-000", everything)
    assert len(first) == CHARGE_BATCH and later not in first and elsewhere not in first
    assert [c.id for c in batch_for("c-L-900", everything)] == ["c-L-900"]
    handled = {c.id for c in together[:CHARGE_BATCH]}
    rest = batch_for("c-L-025", everything, handled)
    assert [c.ledger_line_id for c in rest] == [f"L-{n:03}" for n in range(25, 30)]
    assert batch_for("nope", everything) == []


# Decision 0020: reversals and cost transfers.


def test_a_full_reversal_nets_to_zero():
    original, reversal = charge("L-1", 218000), charge("L-2", -218000, original="L-1")
    nets = net_amounts([original, reversal], RecordState([]))
    assert nets[original.id].net_cents == 0 and nets[original.id].reversed
    assert nets[original.id].corrections == (reversal.id,)
    assert nets[reversal.id].net_cents == -218000 and not nets[reversal.id].reversed


def test_a_partial_correction_leaves_an_ordinary_charge_on_its_net():
    nets = net_amounts(
        [charge("L-1", 40000), charge("L-2", -15000, original="L-1")], RecordState([])
    )
    assert nets["c-L-1"].net_cents == 25000 and not nets["c-L-1"].reversed


def test_a_reversed_reversal_gives_the_original_back_in_full():
    lines = [
        charge("L-1", 218000),
        charge("L-2", -218000, original="L-1"),
        charge("L-3", 218000, original="L-2"),
    ]
    nets = net_amounts(lines, RecordState([]))
    assert nets["c-L-1"].net_cents == 218000 and not nets["c-L-1"].reversed
    assert nets["c-L-2"].reversed  # the reversal is itself fully corrected


def test_a_line_that_adds_money_stands_on_its_own():
    nets = net_amounts(
        [charge("L-1", 40000), charge("L-2", 40000, original="L-1")], RecordState([])
    )
    assert nets["c-L-1"].net_cents == 40000 and nets["c-L-1"].corrections == ()


def test_a_line_on_another_grant_isnt_netted():
    nets = net_amounts(
        [charge("L-1", 40000, grant="other"), charge("L-2", -40000, original="L-1")],
        RecordState([]),
    )
    assert nets["c-L-1"].net_cents == 40000


def test_the_agents_correction_nets_only_once_the_accountant_accepts_it():
    lines = [charge("L-1", 40000), charge("L-2", -40000)]
    suggestion = agent(
        "x1", {"kind": "correction", "charge_id": "c-L-2", "corrects_line_id": "L-1", "reason": "r"}
    )
    assert waiting_records([suggestion]) == [suggestion]
    assert net_amounts(lines, RecordState([suggestion]))["c-L-1"].net_cents == 40000
    accepted = RecordState([suggestion, user("ok", confirm("x1"), 1)])
    assert net_amounts(lines, accepted)["c-L-1"].reversed


def test_a_naming_loop_stops():
    nets = net_amounts(
        [charge("L-1", 100, original="L-2"), charge("L-2", -100, original="L-1")], RecordState([])
    )
    assert set(nets) == {"c-L-1", "c-L-2"}


def test_a_correction_cant_correct_its_own_line():
    data = {"kind": "correction", "charge_id": "c1", "corrects_line_id": "L-1", "reason": "r"}
    assert any("correct itself" in p for p in problems(agent("x1", data), []))


def test_ready_for_closeout_is_worked_out_from_the_status():
    def status(**changes: Any) -> ChargeStatus:
        fields: dict[str, Any] = {
            "grant_id": "g",
            "charge_id": "c1",
            "bucket": "evidence_complete",
            "reasons": (),
            "checklist": (),
            "flagged": False,
        }
        return ChargeStatus.model_validate(fields | changes)

    assert status().ready and ready_for_closeout(status())
    assert not status(snoozed=True).ready
    assert status(bucket="possible_conflict", flagged=True, accepted=True).ready
    assert status(bucket="possible_conflict", reversed=True, net_cents=0).ready
    assert not status(bucket="missing_evidence", ready=True).ready  # what's passed in is ignored
    r = Reason(check="c", problem="p", text="t", bucket=Bucket.NEEDS_HUMAN, dispute_id="d1")
    assert r.dispute_id == "d1"


# Decision 0021: a cost shared by two grants.


def share(agent_cites: bool = True) -> dict[str, Any]:
    passage = "56 of the 96 samples are for this grant"
    if not agent_cites:
        return {
            "share": {"value": "56"},
            "out_of": {"value": "96"},
            "total": {"value": 1000000},
            "note": "The PI's count of samples.",
        }
    return {
        "share": cited(Decimal(56), "56", passage, "f2"),
        "out_of": cited(Decimal(96), "96", passage, "f2"),
        "total": cited(1000000, "$10,000.00", "Total Due: $10,000.00"),
    }


def test_a_part_of_a_bill_rests_on_a_share_or_a_stated_amount():
    b = agent("b1", bill(1000000, "$10,000.00"))
    shared = agent("l1", link(amount=583333, share=share()), 1)
    assert problems(shared, [b]) == []
    assert shared.data.share is not None  # type: ignore[union-attr]
    worked_out = shared.data.share.amount()  # type: ignore[union-attr]
    assert abs(worked_out - 583333) < 1
    stated = cited(583333, "$5,833.33", "Sequencing for grant 1: $5,833.33")
    with pytest.raises(ValidationError):
        agent("l2", link(amount=583333, share=share(), stated_amount=stated))
    with pytest.raises(ValidationError):  # the agent cites the share
        agent("l2", link(amount=583333, share=share(agent_cites=False)))
    typed = user(
        "l3", link(amount=583333, share=share(agent_cites=False))
    )  # the accountant types it
    assert RecordState([typed]).unconfirmed_values(typed) == []
    with pytest.raises(ValidationError):
        user("l4", link(share=share(agent_cites=False) | {"share": {"value": "97"}}))


def test_the_rest_of_a_bill_belongs_to_another_award_as_a_waiting_suggestion():
    b = agent("b1", bill())
    rest: dict[str, Any] = {
        "kind": "remainder",
        "record_id": "b1",
        "other_award": cited("SYN-2300999", "SYN-2300999", "the rest is for SYN-2300999", "f2"),
        "reason": "The email gives the other award.",
    }
    suggestion = agent("r1", rest, 1)
    assert problems(suggestion, [b]) == []
    assert ids(waiting_records([b, suggestion])) == ["r1"]
    assert any(
        "on a bill" in p
        for p in problems(
            agent("r1", rest | {"record_id": "t1"}, 1), [b, user("t1", budget_line())]
        )
    )
    rejected = [b, suggestion, user("no", confirm("r1", decision="rejected"), 2)]
    assert any(
        "rejected the same suggestion" in p for p in problems(agent("r2", rest, 3), rejected)
    )


# Decision 0022: the sign-off.


def statuses(*buckets: str) -> list[ChargeStatus]:
    return [
        ChargeStatus.model_validate(
            {
                "grant_id": "g",
                "charge_id": f"c{i}",
                "bucket": b,
                "reasons": (),
                "checklist": (),
                "flagged": b != "evidence_complete",
            }
        )
        for i, b in enumerate(buckets)
    ]


def test_a_snapshot_and_what_changed_since_sign_off():
    signed = snapshot_of(statuses("evidence_complete", "possible_conflict"), CHARGES, ["charge:c1"])
    assert signed.totals.charges_ready == 1 and signed.totals.ledger_total_cents == 2400
    assert sign_off_state(None, signed) == SignOffStateName.NOT_SIGNED
    assert sign_off_state(signed, signed) == SignOffStateName.SIGNED
    now = snapshot_of(statuses("evidence_complete", "evidence_complete"), CHARGES, [])
    changes = changes_since(signed, now)
    kinds = {c.kind for c in changes}
    assert kinds == {ChangeKind.CHARGE, ChangeKind.PROBLEM_LIST, ChangeKind.TOTAL}
    moved = next(c for c in changes if c.kind == ChangeKind.CHARGE)
    assert (moved.subject, moved.before, moved.after) == (
        "c1",
        "possible_conflict",
        "evidence_complete",
    )
    assert sign_off_state(signed, now) == SignOffStateName.CHANGED


def test_the_stored_sign_off_has_its_report_and_the_request_only_a_note():
    user("s1", sign_off("Signed with one charge open: refund coming."))
    with pytest.raises(ValidationError):
        user("s1", {"kind": "sign_off", "note": "n"})
    request = api.NewRecordInput.model_validate({"data": {"kind": "sign_off", "note": "n"}})
    assert request.data.kind == "sign_off"
    with pytest.raises(ValidationError):  # the request can't carry the server's fields
        api.NewRecordInput.model_validate({"data": sign_off()})


def test_an_accountants_term_may_leave_dated_to_the_server():
    term = budget_line()
    del term["dated"]
    api.NewRecordInput.model_validate({"data": term})
    with pytest.raises(ValidationError):  # the stored term still requires it
        user("t1", term)


# Decision 0025: Gmail and Drive.


def held(grant_id: str = "g") -> HeldMail:
    return HeldMail.model_validate(
        {
            "id": "m1",
            "workspace_id": "w",
            "grant_id": grant_id,
            "sender": "stranger@vendor.example",
            "reason": "unknown_sender",
            "source_ref": "gmail-1",
            "held_at": at(0),
            "files": [
                {
                    "name": "message.eml",
                    "media_type": "message/rfc822",
                    "storage_path": "w/g/held/m1/message.eml",
                    "sha256": "0" * 64,
                }
            ],
        }
    )


def test_held_mail_and_its_actions():
    let_in = user("a1", {"kind": "mail_action", "held_mail_id": "m1", "action": "let_in"})
    assert (
        check_new_record(
            let_in, [], CHARGES, FILES, default_items=defaults, held_mail=[held()], trigger=None
        )
        == []
    )
    assert any(
        "doesn't exist" in p
        for p in check_new_record(let_in, [], CHARGES, FILES, default_items=defaults, trigger=None)
    )
    assert any(
        "isolated" in p
        for p in check_new_record(
            let_in,
            [],
            CHARGES,
            FILES,
            default_items=defaults,
            held_mail=[held("other")],
            trigger=None,
        )
    )
    with pytest.raises(ValidationError):  # only the accountant decides on held mail
        agent("a2", {"kind": "mail_action", "held_mail_id": "m1", "action": "dismiss"})
    assert held().reason == "unknown_sender"
    with pytest.raises(ValidationError):
        HeldMail.model_validate(held().model_dump() | {"reason": "spam"})


def test_a_grants_address_drive_folder_and_an_export_mark():
    g = Grant(id="g", workspace_id="w", address_code="k7m2p9qa", drive_folder_id="1AbC")
    assert g.address_code == "k7m2p9qa"
    export = file("f9").model_copy(update={"exported_from": "application/vnd.google-apps.document"})
    assert EvidenceFile.model_validate(export.model_dump()).exported_from is not None
    progress = CheckerProgress.model_validate(
        {
            "mail_cursor": "42",
            "seen_message_ids": ["a"],
            "drive_versions": [{"grant_id": "g", "drive_file_id": "d", "version": "v1"}],
        }
    )
    assert progress.drive_versions[0].version == "v1"


# Decision 0026: the answer key grows.


def test_the_answer_key_grows_and_older_keys_stay_valid():
    old = load_sample_answer_key()
    assert old.failing_checks == () and old.suggestions == ()
    grown = AnswerKey.model_validate(
        old.model_dump(mode="json")
        | {
            "buckets": [{"line_id": "L-1002", "at": "2026-05-01T00:00:00Z", "bucket": "reversed"}],
            "failing_checks": [
                {
                    "line_id": "L-1002",
                    "at": "2026-02-24T12:00:00Z",
                    "checks": ["period_of_performance"],
                }
            ],
            "checklist_items": [{"line_id": "L-1001", "fields": {"needed": "Packing slip"}}],
            "suggestions": [
                {
                    "kind": "dispute",
                    "line_id": "L-1002",
                    "fields": {"check": "period_of_performance"},
                }
            ],
        }
    )
    assert grown.buckets[0].bucket == "reversed"
    with pytest.raises(ValidationError):
        AnswerKey.model_validate(
            old.model_dump(mode="json")
            | {"buckets": [{"line_id": "L", "at": "2026-05-01T00:00:00Z", "bucket": "done"}]}
        )


# The screen bodies.


def test_the_problem_list_rows_narrow_on_kind_and_have_distinct_keys():
    grant_row = {
        "kind": "grant",
        "problem": {"check": "budget", "problem": "over_limit", "text": "Over.", "flagged": True},
    }
    charge_row = {
        "kind": "charge",
        "charge": CHARGE.model_dump(mode="json"),
        "status": statuses("needs_human")[0].model_dump(mode="json"),
    }
    held_row = {"kind": "held_mail", "held": held().model_dump(mode="json")}
    rows = api.ProblemList.model_validate({"rows": [grant_row, charge_row, held_row]}).rows
    assert [type(r).__name__ for r in rows] == [
        "GrantProblemRow",
        "ChargeProblemRow",
        "HeldMailRow",
    ]
    keys = [api.problem_row_key(r) for r in rows]
    assert len(set(keys)) == 3 and keys[0] == "grant:budget:over_limit"


def test_every_screen_body_has_a_json_schema():
    for name in (
        "GrantSummary",
        "GrantDetail",
        "ProblemList",
        "ChargeRow",
        "ChargeDetail",
        "EvidenceCard",
        "RecordView",
        "Thread",
        "NewMessage",
        "Clock",
        "NewRecordInput",
    ):
        getattr(api, name).model_json_schema()
    clock = api.Clock.model_validate(
        {
            "now": at(0),
            "simulated": True,
            "next_arrival": {"at": at(1), "source": "ledger", "name": "L-1002"},
        }
    )
    assert clock.next_arrival is not None and clock.next_arrival.at == at(1)


def test_a_record_view_and_a_thread_entry():
    r: Record = agent("b1", bill())
    view = api.RecordView(record=r, state=api.RecordState.COUNTS)
    entry = api.Thread.model_validate(
        {"entries": [{"kind": "record", "record": r.model_dump(mode="json"), "state": "waiting"}]}
    )
    assert view.state == "counts" and entry.entries[0].kind == "record"


# Agreed additions: a thread run's subject, and skipped files.


def run(trigger: dict[str, Any], **changes: Any) -> AgentRun:
    fields: dict[str, Any] = {
        "id": "run1",
        "workspace_id": "w",
        "grant_id": "g",
        "trigger": trigger,
        "status": "failed",
        "clock_now": at(0),
        "queued_at": at(0),
    }
    return AgentRun.model_validate(fields | changes)


def test_a_run_started_in_a_thread_names_the_threads_subject():
    asked = {"kind": "thread_message", "id": "m1"}
    failed = run(asked, thread_record_id="t1")
    checks_input = ChecksInput(now=at(1), charges=(), files=(), records=(), failed_runs=(failed,))
    assert checks_input.failed_runs[0].thread_record_id == "t1"
    run(asked, thread_charge_id="c1")
    with pytest.raises(ValidationError):
        run(asked)
    with pytest.raises(ValidationError):
        run(asked, thread_charge_id="c1", thread_record_id="t1")
    with pytest.raises(ValidationError):  # only a thread's run names a thread
        run({"kind": "file", "id": "f1"}, thread_charge_id="c1")


def test_skipped_files_reach_the_checks():
    skipped = SkippedFile.model_validate(
        {
            "workspace_id": "w",
            "grant_id": "g",
            "name": "scan.tiff",
            "source": "gmail",
            "source_ref": "gmail-9",
            "reason": "too_large",
            "skipped_at": at(0),
        }
    )
    checks_input = ChecksInput(
        now=at(1), charges=(), files=(), records=(), skipped_files=(skipped,)
    )
    assert checks_input.skipped_files[0].reason == "too_large"
    with pytest.raises(ValidationError):
        SkippedFile.model_validate(skipped.model_dump() | {"source": "upload"})
    with pytest.raises(ValidationError):
        SkippedFile.model_validate(skipped.model_dump() | {"reason": "corrupt"})


# Agreed: every record the agent writes in a run a thread message started waits.


def test_a_first_link_written_by_a_thread_run_waits():
    b = agent("b1", bill())
    in_thread = agent("l1", link(), 1).model_copy(update={"thread_message_id": "m1"})
    ordinary = agent("l1", link(), 1)
    assert ids(waiting_records([b, in_thread])) == ["l1"]
    assert waiting_records([b, ordinary]) == []
    assert ids(RecordState([b, ordinary]).current()) == ["b1", "l1"]
    confirmed = [b, in_thread, user("ok", confirm("l1"), 2)]
    assert ids(RecordState(confirmed).current()) == ["b1", "l1", "ok"]


def test_the_write_check_makes_a_thread_run_name_its_message():
    b = agent("b1", bill())
    asked = Trigger(kind=TriggerKind.THREAD_MESSAGE, id="m1")
    unmarked = agent("l1", link(), 1).model_copy(update={"read_through_seq": 10})
    marked = unmarked.model_copy(update={"thread_message_id": "m1"})

    def check(new: Record, trigger: Trigger | None) -> list[str]:
        return check_new_record(new, [b], CHARGES, FILES, default_items=defaults, trigger=trigger)

    assert check(marked, asked) == []
    assert any("waits for the accountant" in p for p in check(unmarked, asked))
    assert any("only a record written" in p for p in check(marked, None))
    assert check(unmarked, Trigger(kind=TriggerKind.CHARGE, id="c1")) == []
    with pytest.raises(ValidationError):
        Record.model_validate(user("x", bill()).model_dump() | {"thread_message_id": "m1"})


# Agreed: a text citation's highlight can hold several character ranges.


def test_a_text_highlight_holds_several_ranges_inside_the_passage():
    base: dict[str, Any] = {
        "file_id": "f1",
        "passage": "Sediment core liners\n50 count: $1,240.00",
        "location": {"type": "char_location", "start_char_index": 100, "end_char_index": 140},
    }
    two_lines = [
        {"start_char_index": 100, "end_char_index": 120},
        {"start_char_index": 121, "end_char_index": 140},
    ]
    c = Citation.model_validate(base | {"highlight": two_lines})
    assert c.highlight is not None and len(c.highlight) == 2
    with pytest.raises(ValidationError):  # outside the passage
        Citation.model_validate(
            base | {"highlight": [{"start_char_index": 90, "end_char_index": 110}]}
        )
    pages = {"type": "page_location", "start_page_number": 1, "end_page_number": 2}
    with pytest.raises(ValidationError):  # character ranges are for text
        Citation.model_validate(base | {"location": pages, "highlight": two_lines})
    box = [{"page": 1, "left": 0.1, "top": 0.1, "width": 0.5, "height": 0.02}]
    with pytest.raises(ValidationError):  # boxes are for a PDF
        Citation.model_validate(base | {"highlight": box})
    Citation.model_validate(base | {"location": pages, "highlight": box})


# The review of the staged #39.


def ready_status(**changes: Any) -> ChargeStatus:
    fields: dict[str, Any] = {
        "grant_id": "g",
        "charge_id": "c1",
        "bucket": "evidence_complete",
        "reasons": (),
        "checklist": (),
        "flagged": False,
    }
    return ChargeStatus.model_validate(fields | changes)


def test_d1_ready_is_computed_and_follows_every_change():
    s = ready_status()
    assert s.model_copy(update={"snoozed": True}).ready is False
    assert ready_status(bucket="needs_human", flagged=True, accepted=1).ready is True
    dumped = s.model_dump(mode="json")
    assert dumped["ready"] is True
    assert ChargeStatus.model_validate(dumped | {"ready": False}).ready is True  # read back
    schema = ChargeStatus.model_json_schema(mode="serialization")
    assert "ready" in schema["required"]
    assert "ready" not in ChargeStatus.model_json_schema(mode="validation")["properties"]


def test_d2_a_charge_has_one_current_correction():
    first = user(
        "x1", {"kind": "correction", "charge_id": "c1", "corrects_line_id": "L-2", "reason": "r"}
    )
    second = user(
        "x2", {"kind": "correction", "charge_id": "c1", "corrects_line_id": "L-3", "reason": "r"}, 1
    )
    assert any("already has a current correction" in p for p in problems(second, [first]))
    replacing = second.model_copy(update={"replaces_id": "x1"})
    assert problems(replacing, [first]) == []


def test_d3_a_line_says_what_it_nets_into():
    lines = [
        charge("L-1", 100),
        charge("L-2", -100, original="L-1"),
        charge("L-3", 100, original="L-2"),
    ]
    nets = net_amounts(lines, RecordState([]))
    assert nets["c-L-2"].nets_into == "c-L-1" and nets["c-L-3"].nets_into == "c-L-2"
    assert nets["c-L-1"].nets_into is None
    # Nets aren't additive: the lines that net into another are inside its net.
    assert sum(n.net_cents for n in nets.values() if n.nets_into is None) == 100


def test_d4_signing_off_with_anything_open_needs_a_note():
    open_snapshot = sign_off()
    open_snapshot["snapshot"] = open_snapshot["snapshot"] | {"problem_rows": ["charge:c1"]}
    assert any("needs a note" in p for p in problems(user("s1", open_snapshot), []))
    assert problems(user("s1", open_snapshot | {"note": "Refund coming in March."}), []) == []
    assert any(
        "needs a note" in p for p in problems(user("s1", open_snapshot | {"note": "  "}), [])
    )
    conflict = sign_off()
    conflict["snapshot"]["charges"][0]["bucket"] = "possible_conflict"
    assert any("needs a note" in p for p in problems(user("s1", conflict), []))
    assert problems(user("s1", sign_off()), []) == []  # nothing open, no note needed


def test_d5_a_held_message_has_one_current_decision():
    first = user("a1", {"kind": "mail_action", "held_mail_id": "m1", "action": "dismiss"})
    second = user("a2", {"kind": "mail_action", "held_mail_id": "m1", "action": "let_in"}, 1)

    def check(new: Record) -> list[str]:
        return check_new_record(
            new, [first], CHARGES, FILES, default_items=defaults, held_mail=[held()], trigger=None
        )

    assert any("already has a current decision" in p for p in check(second))
    assert check(second.model_copy(update={"replaces_id": "a1"})) == []


def test_nit1_a_naming_loop_nets_the_same_whatever_the_order():
    lines = [charge("L-1", 100, original="L-2"), charge("L-2", -100, original="L-1")]
    assert net_amounts(lines, RecordState([])) == net_amounts(
        list(reversed(lines)), RecordState([])
    )


def test_nit2_a_correction_cant_contradict_the_ledger():
    named = CHARGE.model_copy(update={"original_line_id": "L-2"})
    other = CHARGES[1]  # ledger line L-2, on this grant
    data = {"kind": "correction", "charge_id": "c1", "corrects_line_id": "L-9", "reason": "r"}
    found = check_new_record(
        user("x1", data), [], [named, other], FILES, default_items=defaults, trigger=None
    )
    assert any("the ledger says" in p for p in found)


def test_nit3_a_reversed_charge_nets_to_zero():
    with pytest.raises(ValidationError):
        ready_status(reversed=True, net_cents=100)


def test_nit4_a_share_matches_to_within_one_cent():
    basis = user("l1", link(amount=583333, share=share(agent_cites=False))).data
    assert basis.share is not None  # type: ignore[union-attr]
    assert basis.share.matches(583333) and basis.share.matches(583334)  # type: ignore[union-attr]
    assert not basis.share.matches(583335)  # type: ignore[union-attr]


def test_nit6_a_handled_trigger_covers_nothing():
    lines = [charge("L-1", 100), charge("L-2", 100)]
    assert batch_for("c-L-1", lines, handled={"c-L-1"}) == []


def test_nit7_a_naive_now_is_refused():
    from datetime import datetime

    from app.contracts.charges import LedgerRow

    row = LedgerRow.model_validate(
        {
            "line_id": "L-1",
            "transaction_date": "2026-01-02",
            "posting_date": "2026-01-04",
            "amount": "12.00",
            "description": "d",
            "account": "a",
        }
    )
    with pytest.raises(ValueError):
        row.arrival(datetime(2026, 1, 1, 9))


def test_nit8_the_snapshot_counts_the_charges_it_totals():
    snap = snapshot_of(statuses("evidence_complete"), CHARGES, [])
    assert snap.totals.charges_total == len(CHARGES) and snap.totals.ledger_total_cents == 2400


def test_nit10_whether_a_message_is_still_held():
    m = held()
    assert still_held(m, RecordState([]), known_senders=())
    assert not still_held(m, RecordState([]), known_senders={"Stranger@Vendor.example"})
    dismissed = user("a1", {"kind": "mail_action", "held_mail_id": "m1", "action": "dismiss"})
    assert not still_held(m, RecordState([dismissed]), known_senders=())
    forged = m.model_copy(update={"reason": "unverified_sender"})
    assert still_held(forged, RecordState([]), known_senders={"stranger@vendor.example"})


def test_an_open_question_trigger_names_its_charge_or_record():
    t = Trigger(kind=TriggerKind.OPEN_QUESTION, id="c1")
    assert run(t.model_dump()).trigger.kind == "open_question"
    with pytest.raises(ValidationError):
        Trigger(kind=TriggerKind.OPEN_QUESTION)
    with pytest.raises(ValidationError):  # it isn't a thread run, so it names no thread
        run(t.model_dump(), thread_charge_id="c1")


# Agreed: an approval rule says what it applies to.


def approval_rule(**changes: Any) -> dict[str, Any]:
    clause = "Funds for Participant Support Costs may not be diverted to other categories"
    rule: dict[str, Any] = {
        "kind": "approval_rule",
        "dated": cited("2023-01-10", "January 10, 2023", file_id="f3"),
        "applies_to": cited("Participant Support Costs", "Participant Support Costs", clause, "f3"),
        "approver": cited("Program Officer", "Program Officer", "the Program Officer", "f3"),
        "scope": cited("moved_out", "may not be diverted", clause, "f3"),
    }
    return rule | changes


def test_an_approval_rule_carries_its_scope_cited():
    rule = agent("t1", approval_rule())
    assert rule.data.scope is not None and rule.data.scope.value == "moved_out"  # type: ignore[union-attr]
    assert problems(rule, []) == []
    agent("t2", approval_rule(scope=None))  # unclear: the agent flags the term instead
    with pytest.raises(ValidationError):  # the agent cites it
        agent("t3", approval_rule(scope={"value": "every_charge"}))
    user("t4", approval_rule(scope={"value": "every_charge"}))  # the accountant may type it
    with pytest.raises(ValidationError):
        user("t5", approval_rule(scope={"value": "some_charges"}))
    wrong_text = approval_rule(
        scope=cited("moved_out", "every charge", "the Program Officer", "f3")
    )
    assert any("doesn't contain" in p for p in problems(agent("t6", wrong_text), []))


# The re-review of the staged #39.


def thread_link(id: str = "l1", hours: float = 1) -> Record:
    return agent(id, link(), hours).model_copy(update={"thread_message_id": "m1"})


def test_c1_an_ordinary_run_repeating_a_waiting_thread_record_waits_too():
    b = agent("b1", bill())
    again = agent("l2", link(), 2)  # the open_question run writes the same link
    state = RecordState([b, thread_link(), again])
    assert ids(state.waiting()) == ["l1", "l2"]
    assert ids(state.current()) == ["b1"]
    # Once the accountant decides on the thread run's link, a later one counts as usual.
    decided = RecordState([b, thread_link(), user("ok", confirm("l1"), 2), agent("l3", link(), 3)])
    assert decided.waits("l3") is True  # a second link beside the confirmed one waits anyway


def test_c1_an_ordinary_run_cant_repeat_a_rejected_thread_record():
    b = agent("b1", bill())
    written = [b, thread_link(), user("no", confirm("l1", decision="rejected"), 2)]
    found = problems(agent("l2", link(), 3), written)
    assert any("rejected the same suggestion" in p for p in found)
    arrived = [*FILES, file("f9", arrived_hours=2.5)]
    assert problems(agent("l2", link(), 3), written, arrived) == []


def test_c1_the_same_holds_for_a_checklist_item():
    item: dict[str, Any] = {"kind": "checklist_item", "charge_id": "c1", "needed": "Packing slip"}
    from_thread = agent("i1", item).model_copy(update={"thread_message_id": "m1"})
    rejected = [from_thread, user("no", confirm("i1", decision="rejected"), 1)]
    same = agent("i2", item | {"needed": "packing  slip"}, 2)
    assert any("rejected the same suggestion" in p for p in problems(same, rejected))
    assert RecordState([from_thread, agent("i3", item, 1)]).waits("i3") is True
    other = agent("i4", item | {"needed": "Delivery receipt"}, 2)
    assert problems(other, rejected) == []


def test_c2_the_write_check_needs_the_trigger():
    with pytest.raises(TypeError):
        check_new_record(agent("b1", bill()), [], CHARGES, FILES, default_items=defaults)  # type: ignore[call-arg]


def test_nit1_a_let_in_stands():
    let_in = user("a1", {"kind": "mail_action", "held_mail_id": "m1", "action": "let_in"})

    def check(new: Record) -> list[str]:
        return check_new_record(
            new, [let_in], CHARGES, FILES, default_items=defaults, held_mail=[held()], trigger=None
        )

    assert any(
        "decision stands" in p
        for p in check(user("x", {"kind": "retraction"}, 1, replaces_id="a1"))
    )
    dismiss = user(
        "a2",
        {"kind": "mail_action", "held_mail_id": "m1", "action": "dismiss"},
        1,
        replaces_id="a1",
    )
    assert any("decision stands" in p for p in check(dismiss))


# The third review of the staged #39.


def test_r3_1_the_agents_record_comes_with_its_runs_trigger():
    def check(new: Record, trigger: Trigger | None) -> list[str]:
        return check_new_record(new, [], CHARGES, FILES, default_items=defaults, trigger=trigger)

    clock = Trigger(kind=TriggerKind.CLOCK)
    read = agent("b1", bill()).model_copy(update={"read_through_seq": 10})
    assert any("needs the trigger" in p for p in check(read, None))
    assert check(read, clock) == []
    assert any("isn't written by an agent run" in p for p in check(user("b1", bill()), clock))
    assert check(user("b1", bill()), None) == []


def from_thread(record: Record) -> Record:
    return record.model_copy(update={"thread_message_id": "m1"})


def test_r3_2_a_rejected_thread_answer_cant_come_back_in_an_ordinary_run():
    written = [
        from_thread(agent("j1", answer("supports"))),
        user("no", confirm("j1", decision="rejected"), 1),
    ]
    found = problems(agent("j2", answer("supports"), 2), written)
    assert any("rejected the same suggestion" in p for p in found)
    assert problems(agent("j3", answer("contradicts"), 2), written) == []  # toward a concern


def test_r3_2_a_later_first_answer_waits_while_the_thread_copy_waits():
    state = RecordState(
        [from_thread(agent("j1", answer("supports"))), agent("j2", answer("supports"), 1)]
    )
    assert ids(state.waiting()) == ["j1", "j2"]


def test_r3_2_flags_assignments_and_facts_are_matched_too():
    flag = answer("unsure", question="flag", text="Is this a duplicate?")
    flagged = [from_thread(agent("f1", flag)), user("no", confirm("f1", decision="rejected"), 1)]
    assert any("rejected the same suggestion" in p for p in problems(agent("f2", flag, 2), flagged))

    line = user("t1", budget_line())
    assign = {
        "kind": "budget_assignment",
        "charge_id": "c1",
        "record_id": "t1",
        "reason": "Supplies.",
    }
    assigned = [
        line,
        from_thread(agent("a1", assign)),
        user("no", confirm("a1", decision="rejected"), 1),
    ]
    assert any(
        "rejected the same suggestion" in p for p in problems(agent("a2", assign, 2), assigned)
    )

    read = [from_thread(agent("b1", bill())), user("no", confirm("b1", decision="rejected"), 1)]
    assert any("rejected the same suggestion" in p for p in problems(agent("b2", bill(), 2), read))
    assert problems(agent("b3", bill(1300, "$13.00"), 2), read) == []  # a different reading


def test_a_held_file_keeps_the_sent_date_it_takes_when_let_in():
    """Ruling 43: the sent date the evidence file takes as its document date."""
    from datetime import date

    from app.contracts.mail import HeldFile

    f = HeldFile(
        name="message.eml",
        media_type="message/rfc822",
        storage_path="w/g/held/m1/message.eml",
        sha256="0" * 64,
        document_date=date(2026, 2, 21),
    )
    assert HeldFile.model_validate_json(f.model_dump_json()).document_date == date(2026, 2, 21)
    assert held().files[0].document_date is None  # none given


def test_an_emails_reading_text_maps_back_to_the_stored_file():
    """Ruling 45: the viewer shows the text the agent read, mapped to stored positions."""
    reading = api.ReadingView(
        text="Date: Feb 21, 2026\n\nTotal: $2,180.00",
        segments=(api.TextSegment(stored_start=120, reading_start=20, length=16),),
    )
    link = api.FileLink(url="https://example.invalid/signed", expires_at=at(1), reading=reading)
    back = api.FileLink.model_validate_json(link.model_dump_json())
    assert back.reading is not None and back.reading.segments[0].stored_start == 120
    assert api.FileLink(url="u", expires_at=at(1)).reading is None  # every other file
    with pytest.raises(ValidationError):
        api.TextSegment(stored_start=0, reading_start=0, length=0)
