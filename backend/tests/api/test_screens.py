"""The screen bodies (#22 as agreed, PR 40's names) over the sample grant (contracts.md
section 15), with the checks faked."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest

from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecksInput, ChecksOutput, Problem
from app.contracts.fixtures import SampleGrant
from app.contracts.records import DefaultItem, Judgment, Record
from app.contracts.runs import Trigger, TriggerKind
from app.db import store
from app.db.clock import ClockError, grant_now, move_grant_clock, next_arrival
from app.db.jobs import NORMAL_PRIORITY, THREAD_PRIORITY, grant_catching_up
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult
from app.db.recheck import recheck_grant
from tests.api.conftest import Api
from tests.db.platform_fixtures import (
    FakeAgent,
    FakeChecks,
    FakeStorage,
    run_worker_until_idle,
    sample_into_db,
)

APRIL_10 = datetime(2026, 4, 10, 17, tzinfo=UTC)  # after the extension is confirmed
APRIL_9 = datetime(2026, 4, 9, 17, tzinfo=UTC)  # the extension waits to be confirmed


def _sample(api: Api, clock: datetime = APRIL_10) -> SampleGrant:
    sample = sample_into_db(api.platform, api.user_id, clock)
    with transaction(api.platform.pool) as conn:
        recheck_grant(
            conn, api.platform.checks, sample.grant, clock, Trigger(kind=TriggerKind.CLOCK)
        )
    return sample


def _id(sample: SampleGrant, name: str) -> str:
    """A sample record's or file's stored ID from its name in the sample."""
    for x in [*sample.records, *sample.files, *sample.charges]:
        if x.id.rsplit("-", 1)[0] == name:
            return x.id
    raise KeyError(name)


def _checks(api: Api) -> FakeChecks:
    checks = api.platform.checks
    assert isinstance(checks, FakeChecks)
    return checks


def _get(api: Api, path: str) -> Any:
    response = api.client.get(path, headers=api.headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_grant_page_shows_terms_in_force_budget_and_closeout(api: Api) -> None:
    sample = _sample(api)
    _checks(api).notes = ["Other is over its budget."]
    detail = _get(api, f"/grants/{sample.grant.id}")
    s = detail["summary"]
    assert s["end_date"] == "2027-01-31"
    assert (s["charges_ready"], s["charges_total"], s["waiting"]) == (2, 2, 0)
    assert s["next_closeout"] == {"date": "2026-11-02", "label": "First Notice of Expiration"}
    assert s["bucket_counts"]["evidence_complete"] == 2
    assert [t["state"] for t in detail["terms"]] == ["counts"] * 11
    budget = detail["budget"]
    spent = {line["line"]["data"]["name"]["value"]: line["spent_cents"] for line in budget["lines"]}
    assert spent == {
        "Participant Support Costs": 0,
        "Other Direct Costs": 342000,
        "Materials and Supplies": 124000,
        "Other": 218000,
    }
    assert (budget["limit_cents"], budget["spent_cents"]) == (12000000, 342000)
    assert [n["text"] for n in detail["grant_notes"]] == ["Other is over its budget."]
    assert detail["sign_off"] == {
        "state": "not_signed",
        "sign_off": None,
        "changes": [],
        "unavailable_reason": None,
    }

    [row] = _get(api, f"/workspaces/{sample.workspace.id}/grants")
    assert row == s


def test_the_problem_list_is_sorted_by_the_server(api: Api) -> None:
    checks = _checks(api)
    checks.grant_problems = [Problem(check="budget", problem="over_limit", text="Over the limit.")]
    checks.buckets = {"L-1001": Bucket.NEEDS_HUMAN, "L-1002": Bucket.POSSIBLE_CONFLICT}
    sample = sample_into_db(api.platform, api.user_id, APRIL_9)
    checks.record_problems = {
        _id(sample, "rec-bill-inv-1001"): [Problem(check="sums", problem="over", text="Over.")]
    }
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_9, Trigger(kind=TriggerKind.CLOCK))
    rows = _get(api, f"/grants/{sample.grant.id}/problems")["rows"]
    assert [r["kind"] for r in rows] == ["grant", "record", "terms_waiting", "charge", "charge"]
    assert rows[2]["text"] == "1 term waiting to be confirmed"
    assert rows[2]["file"]["name"] == "extension_notice.txt"
    assert [r["charge"]["ledger_line_id"] for r in rows[3:]] == ["L-1002", "L-1001"]
    detail = _get(api, f"/grants/{sample.grant.id}")
    assert detail["summary"]["on_problem_list"] == 5
    assert [t["state"] for t in detail["terms"]][0] == "waiting"
    assert detail["summary"]["end_date"] == "2026-01-31"


def test_the_charge_page(api: Api) -> None:
    sample = _sample(api)
    charge_id = _id(sample, "chg-l-1001")
    detail = _get(api, f"/charges/{charge_id}")
    assert detail["budget_line"]["data"]["name"]["value"] == "Materials and Supplies"
    [link] = detail["links"]
    assert link["record"]["data"]["kind"] == "bill" and link["file"]["name"] == "invoice_1001.txt"
    assert link["values"] and all(v["confirmed"] and v["how"] == "found" for v in link["values"])
    [answer] = detail["answers"]
    assert answer["judgment"]["data"]["answer"] == "supports" and not answer["out_of_date"]
    assert detail["account_categories"] == ["materials_and_supplies"]
    [entry] = detail["history"]
    assert entry["text"] == "Apr 10, 2026 · time passed · Evidence complete"
    assert entry["entry"]["trigger"] == {"kind": "clock", "id": None}
    assert [i["kind"] for i in detail["thread"]["entries"]] == ["status"]
    assert detail["thread"]["agent_run"] is None
    response = api.client.get(f"/charges/{_id(sample, 'chg-l-1002')}x", headers=api.headers)
    assert response.status_code == 404


def test_a_charge_that_hasnt_arrived_is_404(api: Api) -> None:
    sample = _sample(api, datetime(2025, 12, 1, tzinfo=UTC))
    assert (
        api.client.get(f"/charges/{_id(sample, 'chg-l-1002')}", headers=api.headers).status_code
        == 404
    )


def test_a_thread_question_is_queued_ahead_and_the_thread_says_so(api: Api) -> None:
    sample = _sample(api)
    charge_id = _id(sample, "chg-l-1002")
    response = api.client.post(
        f"/charges/{charge_id}/thread", json={"text": "Is this run 7?"}, headers=api.headers
    )
    assert response.status_code == 201, response.text
    assert response.json()["author"] == "user"
    thread = _get(api, f"/charges/{charge_id}/thread")
    assert [i["kind"] for i in thread["entries"]] == ["status", "message"]
    assert thread["agent_run"]["status"] == "queued"
    with transaction(api.platform.pool) as conn:
        [job] = conn.execute("select priority from procrastinate_jobs").fetchall()
    assert job["priority"] == THREAD_PRIORITY


def test_a_records_thread_follows_its_correction(api: Api) -> None:
    sample = _sample(api)
    old = _id(sample, "rec-person-pi")
    # Only a record with a problem has a thread: give this one the agent's flag.
    checks = _checks(api)
    checks.record_problems = {old: [Problem(check="flag", problem="unsure", text="Check this.")]}
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_10, Trigger(kind=TriggerKind.CLOCK))
    checks.record_problems = {}
    correction = api.client.post(
        f"/grants/{sample.grant.id}/records",
        json={
            "replaces_id": old,
            "data": {
                "kind": "person",
                "name": {"value": "Dr. Robin Example"},
                "role": {"value": "Principal Investigator"},
                "email": {"value": "robin.example@university.example"},
            },
        },
        headers=api.headers,
    )
    assert correction.status_code == 201, correction.text
    posted = api.client.post(f"/records/{old}/thread", json={"text": "Right?"}, headers=api.headers)
    assert posted.json()["record_id"] == correction.json()["id"]
    entries = _get(api, f"/records/{old}/thread")["entries"]
    # The award terms' confirmation, the flag's status, the correction and the status it
    # cleared, then the message.
    kinds = [i["kind"] for i in entries]
    assert kinds[0] == "record" and kinds[-1] == "message"
    corrected = [e for e in entries if e["kind"] == "record" and e["record"]["replaces_id"] == old]
    assert [e["record"]["id"] for e in corrected] == [correction.json()["id"]]


def test_a_record_with_no_problem_has_no_thread(api: Api) -> None:
    sample = _sample(api)
    response = api.client.post(
        f"/records/{_id(sample, 'rec-person-pi')}/thread",
        json={"text": "Right?"},
        headers=api.headers,
    )
    assert response.status_code == 422
    assert "problem" in response.json()["detail"][0]


def test_evidence_cards_show_facts_and_what_they_pay_for(api: Api) -> None:
    sample = _sample(api)
    cards = _get(api, f"/grants/{sample.grant.id}/evidence")
    assert [c["file"]["name"] for c in cards] == [
        "extension_notice.txt",
        "sequencing_statement.eml",
        "invoice_1001.txt",
        "award_letter.txt",
    ]
    invoice = cards[2]
    [fact] = invoice["facts"]
    assert fact["record"]["data"]["kind"] == "bill" and fact["state"] == "counts"
    [link] = fact["links"]
    assert link["charge"]["ledger_line_id"] == "L-1001"
    assert len(cards[3]["facts"]) == 10


def test_sign_off_waits_for_the_agent_and_needs_a_note_when_something_is_open(api: Api) -> None:
    checks = _checks(api)
    checks.buckets = {"L-1002": Bucket.POSSIBLE_CONFLICT}
    sample = _sample(api)
    path = f"/grants/{sample.grant.id}/records"
    api.client.post(
        f"/charges/{_id(sample, 'chg-l-1002')}/thread", json={"text": "?"}, headers=api.headers
    )
    refused = api.client.post(path, json={"data": {"kind": "sign_off"}}, headers=api.headers)
    assert refused.status_code == 422 and "still working" in refused.json()["detail"][0]
    with transaction(api.platform.pool) as conn:
        conn.execute(
            "update public.agent_runs set status = 'done' where grant_id = %s", (sample.grant.id,)
        )
    refused = api.client.post(path, json={"data": {"kind": "sign_off"}}, headers=api.headers)
    assert refused.status_code == 422 and "needs a note" in refused.json()["detail"][0]
    signed = api.client.post(
        path,
        json={"data": {"kind": "sign_off", "note": "L-1002 is explained."}},
        headers=api.headers,
    )
    assert signed.status_code == 201, signed.text
    record = signed.json()
    assert record["data"]["note"] == "L-1002 is explained."
    # The report signed is stored, with its checksum, and fetched through the sign-off.
    stored = api.client.get(f"/records/{record['id']}/report", headers=api.headers)
    assert stored.status_code == 200 and stored.content.startswith(b"%PDF")
    import hashlib

    assert hashlib.sha256(stored.content).hexdigest() == record["data"]["report_sha256"]
    state = _get(api, f"/grants/{sample.grant.id}")["sign_off"]
    assert state["state"] == "signed" and state["sign_off"]["id"] == record["id"]
    # A later change shows as "changed since sign-off" with what changed.
    checks.buckets = {}
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_10, Trigger(kind=TriggerKind.CLOCK))
    state = _get(api, f"/grants/{sample.grant.id}")["sign_off"]
    assert state["state"] == "changed"
    assert any(c["kind"] == "charge" for c in state["changes"])


def test_a_sign_off_needs_a_note_while_any_charge_isnt_ready(api: Api) -> None:
    """An unflagged Missing evidence charge isn't on the problem list, but it's still open."""
    checks = _checks(api)
    checks.buckets = {"L-1002": Bucket.MISSING_EVIDENCE}  # not flagged by the fake
    sample = _sample(api)
    assert _get(api, f"/grants/{sample.grant.id}/problems")["rows"] == []
    refused = api.client.post(
        f"/grants/{sample.grant.id}/records",
        json={"data": {"kind": "sign_off"}},
        headers=api.headers,
    )
    assert refused.status_code == 422 and "needs a note" in refused.json()["detail"][0]


def test_the_report_route_gives_the_draft(api: Api) -> None:
    sample = _sample(api)
    path = f"/grants/{sample.grant.id}/report"
    response = api.client.get(path, headers=api.headers)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")
    assert response.headers["content-type"] == "application/pdf"
    assert "SYN-2300117" in response.headers["content-disposition"]


# The grant's clock (decision 0023, issue 165). It moves through the clock module; the
# sample timeline's routes drive it.


def _move(api: Api, sample: SampleGrant, to: datetime | None = None) -> datetime:
    return move_grant_clock(api.platform, sample.grant.id, to)


def _catching_up(api: Api, sample: SampleGrant) -> bool:
    with transaction(api.platform.pool) as conn:
        return grant_catching_up(conn, sample.grant.id)


def _now(api: Api, sample: SampleGrant) -> datetime:
    with transaction(api.platform.pool) as conn:
        return grant_now(conn, sample.grant.id)


def test_a_grant_on_the_real_date_cant_move(api: Api) -> None:
    sample = _sample(api)
    with transaction(api.platform.pool) as conn:
        conn.execute("update public.grants set clock_now = null where id = %s", (sample.grant.id,))
        assert next_arrival(conn, sample.grant.id) is None
    with pytest.raises(ClockError, match="real date"):
        _move(api, sample)


def test_the_clock_finds_the_next_arrival_and_only_moves_forward(api: Api) -> None:
    sample = _sample(api, datetime(2025, 11, 13, tzinfo=UTC))
    with transaction(api.platform.pool) as conn:
        arrival = next_arrival(conn, sample.grant.id)
    assert arrival is not None and (arrival.source, arrival.name) == ("ledger", "L-1001")
    with pytest.raises(ClockError, match="forward"):
        _move(api, sample, datetime(2025, 1, 1, tzinfo=UTC))
    assert _move(api, sample) == datetime(2025, 11, 14, tzinfo=UTC)
    assert _now(api, sample) == datetime(2025, 11, 14, tzinfo=UTC)
    # The grant's summary carries its now.
    [summary] = _get(api, f"/workspaces/{sample.workspace.id}/grants")
    assert summary["now"] == "2025-11-14T00:00:00Z"
    with transaction(api.platform.pool) as conn:
        arrival = next_arrival(conn, sample.grant.id)
    assert arrival is not None and (arrival.source, arrival.name) == (
        "gmail",
        "sequencing_statement.eml",
    )


def test_a_jump_is_replayed_in_arrival_order(api: Api) -> None:
    sample = _sample(api, datetime(2025, 10, 1, tzinfo=UTC))
    _move(api, sample, datetime(2025, 11, 20, tzinfo=UTC))
    assert _catching_up(api, sample)
    with transaction(api.platform.pool) as conn:
        runs = sorted(store.list_runs(conn, sample.grant.id), key=lambda r: r.clock_now)
        jobs = conn.execute("select args from procrastinate_jobs order by id").fetchall()
        history = store.status_history(conn, charge_id=_id(sample, "chg-l-1001"))
    # The closeout window of the old end date opened on Nov 2, then the invoice, then L-1001.
    assert [(r.trigger.kind, r.clock_now.date().isoformat()) for r in runs] == [
        (TriggerKind.CLOCK, "2025-11-02"),
        (TriggerKind.FILE, "2025-11-12"),
        (TriggerKind.CHARGE, "2025-11-14"),
    ]
    assert [j["args"]["run_id"] for j in jobs] == [r.id for r in runs]
    # Statuses past the first catch-up wait for the runs: none yet for L-1001.
    assert history == []
    run_worker_until_idle(str(api.platform.pool.conninfo))
    with transaction(api.platform.pool) as conn:
        history = store.status_history(conn, charge_id=_id(sample, "chg-l-1001"))
    # The charge's first status is stamped on its arrival, with the charge as its trigger.
    assert history[0].changed_at == datetime(2025, 11, 14, tzinfo=UTC)
    assert history[0].trigger.kind == TriggerKind.CHARGE
    assert not _catching_up(api, sample)


def test_a_thread_question_during_a_catch_up_waits_for_it(api: Api) -> None:
    sample = _sample(api, datetime(2025, 11, 13, tzinfo=UTC))
    _move(api, sample, datetime(2025, 11, 20, tzinfo=UTC))
    api.client.post(
        f"/charges/{_id(sample, 'chg-l-1001')}/thread", json={"text": "?"}, headers=api.headers
    )
    with transaction(api.platform.pool) as conn:
        priorities = [
            j["priority"]
            for j in conn.execute("select priority from procrastinate_jobs order by id")
        ]
    # The closeout review (its window is open), L-1001's run, then the question.
    assert priorities == [NORMAL_PRIORITY, NORMAL_PRIORITY, NORMAL_PRIORITY]


def test_a_move_to_exactly_the_next_arrival_is_a_catch_up_until_its_run_finishes(
    api: Api,
) -> None:
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)
    tries: list[TriggerKind] = []

    def behave(i: AgentInput) -> AgentResult:
        tries.append(i.run.trigger.kind)
        if len(tries) == 1:
            raise RuntimeError("overloaded")  # a retry keeps the catch-up mark
        return AgentResult()

    agent.behave = behave
    sample = _sample(api, datetime(2025, 11, 13, tzinfo=UTC))
    charge = _id(sample, "chg-l-1001")
    assert _move(api, sample) == datetime(2025, 11, 14, tzinfo=UTC)
    assert _catching_up(api, sample)

    def ask() -> int:
        api.client.post(f"/charges/{charge}/thread", json={"text": "?"}, headers=api.headers)
        with transaction(api.platform.pool) as conn:
            row = conn.execute(
                "select priority from procrastinate_jobs order by id desc limit 1"
            ).fetchone()
        assert row is not None
        return row["priority"]

    assert ask() == NORMAL_PRIORITY  # asked right after the move: it waits
    run_worker_until_idle(str(api.platform.pool.conninfo))
    # The closeout review (its window is open) fails once and is retried in its place,
    # then L-1001's run, then the question.
    assert tries[:4] == [
        TriggerKind.CLOCK,
        TriggerKind.CLOCK,
        TriggerKind.CHARGE,
        TriggerKind.THREAD_MESSAGE,
    ]
    assert not _catching_up(api, sample)
    assert ask() == THREAD_PRIORITY  # the catch-up is done: a question goes first again


def test_charges_whose_only_reasons_point_at_a_term_are_covered_by_its_row(api: Api) -> None:
    checks = _checks(api)
    sample = sample_into_db(api.platform, api.user_id, APRIL_10)
    rule = _id(sample, "rec-approval-rule")
    checks.buckets = {"L-1001": Bucket.NEEDS_HUMAN, "L-1002": Bucket.NEEDS_HUMAN}
    checks.reason_records = {"L-1001": [rule], "L-1002": [rule]}
    checks.record_problems = {rule: [Problem(check="approvals", problem="unplaced", text="?")]}
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_10, Trigger(kind=TriggerKind.CLOCK))
    rows = _get(api, f"/grants/{sample.grant.id}/problems")["rows"]
    assert [(r["kind"], r["record"]["id"]) for r in rows] == [("record", rule)]


def test_a_waiting_term_with_a_problem_stays_on_its_documents_row_and_is_counted(
    api: Api,
) -> None:
    checks = _checks(api)
    sample = sample_into_db(api.platform, api.user_id, APRIL_9)
    extension = _id(sample, "rec-period-extension")
    waiting = Problem(check="terms", problem="waiting", text="Waiting to be confirmed.")
    disagree = Problem(check="terms", problem="disagree", text="Two end dates disagree.")
    checks.record_problems = {extension: [waiting, disagree]}
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_9, Trigger(kind=TriggerKind.CLOCK))
    rows = _get(api, f"/grants/{sample.grant.id}/problems")["rows"]
    assert [(r["kind"], r.get("text")) for r in rows] == [
        ("terms_waiting", "1 term waiting, 1 flagged")
    ]
    term = _get(api, f"/grants/{sample.grant.id}")["terms"][0]
    assert term["state"] == "waiting"
    assert [p["problem"] for p in term["status"]["problems"]] == ["waiting", "disagree"]

    # Once confirmed, the term's own problem is a row of its own.
    checks.record_problems = {extension: [disagree]}
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_10, Trigger(kind=TriggerKind.CLOCK))
        conn.execute(
            "update public.grants set clock_now = %s where id = %s",
            (APRIL_10, sample.grant.id),
        )
    rows = _get(api, f"/grants/{sample.grant.id}/problems")["rows"]
    assert [(r["kind"], r["record"]["id"]) for r in rows] == [("record", extension)]


class _LinkedChecks(FakeChecks):
    """A charge is Evidence complete once a link to it counts, and Missing evidence before;
    missing evidence is flagged 60 days after the posting date, as the checks do. Default
    items are the sample grant's own."""

    defaults: dict[str, tuple[DefaultItem, ...]] = {}

    def default_items(self, charge: Charge, records: Sequence[Record], /) -> Sequence[DefaultItem]:
        return self.defaults.get(charge.ledger_line_id, ())

    def run_checks(self, checks_input: ChecksInput, /) -> ChecksOutput:
        from datetime import timedelta

        from app.contracts.checks import ChargeStatus, Reason
        from app.contracts.rules import RecordState

        state = RecordState(checks_input.records, checks_input.files)
        linked = {r.charge_id for r in state.current() if r.kind == "link"}
        statuses = []
        for c in checks_input.charges:
            bucket = Bucket.EVIDENCE_COMPLETE if c.id in linked else Bucket.MISSING_EVIDENCE
            late = checks_input.now.date() >= c.posting_date + timedelta(days=60)
            reason = Reason(check="checklist", problem=bucket.value, text="t", bucket=bucket)
            statuses.append(
                ChargeStatus(
                    grant_id=c.grant_id,
                    charge_id=c.id,
                    bucket=bucket,
                    reasons=(reason,),
                    checklist=(),
                    flagged=bucket == Bucket.MISSING_EVIDENCE and late,
                )
            )
        out = super().run_checks(checks_input)
        return out.model_copy(update={"charges": tuple(statuses)})


def test_a_jump_records_no_late_flag_the_stepped_clock_wouldnt(api: Api) -> None:
    """Decision 0023: Feb 1 to May 1 gives L-1002 Evidence complete on Feb 24, never flagged."""
    checks = _LinkedChecks()
    api.platform.checks = checks
    feb_1 = datetime(2026, 2, 1, tzinfo=UTC)
    sample = sample_into_db(api.platform, api.user_id, feb_1)
    checks.defaults = sample.default_items
    # The agent's records after Feb 1 are held back; its catch-up runs write them, each at
    # the arrival time it works as of.
    held = [r for r in sample.records if r.written_at > feb_1]
    with transaction(api.platform.pool) as conn:
        conn.execute(
            "delete from public.records where grant_id = %s and written_at > %s",
            (sample.grant.id, feb_1),
        )
        recheck_grant(conn, checks, sample.grant, feb_1, Trigger(kind=TriggerKind.CLOCK))
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        return AgentResult(
            records=[
                r.model_copy(update={"read_through_seq": i.run.read_through_seq})
                for r in held
                if r.author == "agent" and r.written_at == i.run.clock_now
            ]
        )

    agent.behave = behave
    _move(api, sample, datetime(2026, 5, 1, tzinfo=UTC))
    run_worker_until_idle(str(api.platform.pool.conninfo))
    with transaction(api.platform.pool) as conn:
        history = store.status_history(conn, charge_id=_id(sample, "chg-l-1002"))
    first = history[0]
    assert first.changed_at == datetime(2026, 2, 24, tzinfo=UTC)
    assert first.status.bucket == Bucket.EVIDENCE_COMPLETE  # pyright: ignore[reportAttributeAccessIssue]
    assert not any(row.status.flagged for row in history)


def test_a_possible_conflict_charge_stays_on_the_list_beside_its_terms_problem(api: Api) -> None:
    """Only Needs a human reasons pointing at a term with its own row are covered by it."""
    checks = _checks(api)
    sample = sample_into_db(api.platform, api.user_id, APRIL_10)
    period = _id(sample, "rec-period")
    checks.buckets = {"L-1002": Bucket.POSSIBLE_CONFLICT}
    checks.reason_records = {"L-1002": [period]}
    checks.record_problems = {period: [Problem(check="terms", problem="disagree", text="!")]}
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_10, Trigger(kind=TriggerKind.CLOCK))
    rows = _get(api, f"/grants/{sample.grant.id}/problems")["rows"]
    assert [r["kind"] for r in rows] == ["record", "charge"]


def test_the_thread_shows_any_run_that_will_reach_it(api: Api) -> None:
    sample = _sample(api)
    charge_id = _id(sample, "chg-l-1002")
    with transaction(api.platform.pool) as conn:
        from app.db.jobs import queue_run

        queue_run(conn, sample.grant, Trigger(kind=TriggerKind.CHARGE, id=charge_id), APRIL_10)
    thread = _get(api, f"/charges/{charge_id}/thread")
    assert thread["agent_run"]["trigger"] == {"kind": "charge", "id": charge_id}
    other = _get(api, f"/charges/{_id(sample, 'chg-l-1001')}/thread")
    assert other["agent_run"] is None


def test_the_closeout_review_is_queued_inside_an_open_window_and_for_a_new_end_date(
    api: Api,
) -> None:
    """Inside the window already: the next move queues it. A new end date gets its own."""
    sample = _sample(api, datetime(2025, 12, 1, tzinfo=UTC))  # window opened Nov 2, 2025
    _move(api, sample, datetime(2025, 12, 11, tzinfo=UTC))
    with transaction(api.platform.pool) as conn:
        reviews = [r for r in store.list_runs(conn, sample.grant.id) if r.trigger.kind == "clock"]
    assert [r.clock_now.date().isoformat() for r in reviews] == ["2025-12-01"]
    # The extension (end Jan 31, 2027) is confirmed on Apr 10, 2026: its window opens
    # Nov 2, 2026, and a move past it queues a review for the new end date.
    _move(api, sample, datetime(2026, 11, 5, tzinfo=UTC))
    with transaction(api.platform.pool) as conn:
        reviews = [r for r in store.list_runs(conn, sample.grant.id) if r.trigger.kind == "clock"]
    assert sorted(r.clock_now.date().isoformat() for r in reviews) == ["2025-12-01", "2026-11-02"]


def test_the_grant_page_lists_reusable_notes_and_term_values(api: Api) -> None:
    sample = _sample(api)
    l1001 = _id(sample, "chg-l-1001")
    note = api.client.post(
        f"/grants/{sample.grant.id}/records",
        json={
            "data": {
                "kind": "accepted_reason",
                "charge_id": l1001,
                "reason": {"check": "fake", "problem": "evidence_complete"},
                "note": "Lab supplies from this vendor are standard.",
                "reusable": True,
            }
        },
        headers=api.headers,
    )
    assert note.status_code == 201, note.text
    detail = _get(api, f"/grants/{sample.grant.id}")
    [view] = detail["reusable_notes"]
    assert view["note"]["id"] == note.json()["id"] and view["charge"]["id"] == l1001
    assert view["amount_limit_cents"] == 124000
    period = next(
        t for t in detail["terms"] if t["record"]["data"]["kind"] == "period_of_performance"
    )
    assert period["values"] and all(v["confirmed"] for v in period["values"])
    assert detail["sign_off"] == {
        "state": "not_signed",
        "sign_off": None,
        "changes": [],
        "unavailable_reason": None,
    }


def test_a_second_move_during_a_catch_up_records_no_late_flag(api: Api) -> None:
    """Feb 1 to Feb 25, then to Jun 1 before the agent has run: L-1002 is Evidence complete
    on Feb 24, never flagged, and time alone adds no row while its status holds."""
    checks = _LinkedChecks()
    api.platform.checks = checks
    feb_1 = datetime(2026, 2, 1, tzinfo=UTC)
    sample = sample_into_db(api.platform, api.user_id, feb_1)
    checks.defaults = sample.default_items
    held = [r for r in sample.records if r.written_at > feb_1]
    with transaction(api.platform.pool) as conn:
        conn.execute(
            "delete from public.records where grant_id = %s and written_at > %s",
            (sample.grant.id, feb_1),
        )
        # Nothing arrives between the two moves.
        conn.execute(
            "delete from public.evidence_files where id = %s",
            (_id(sample, "file-extension-notice"),),
        )
        recheck_grant(conn, checks, sample.grant, feb_1, Trigger(kind=TriggerKind.CLOCK))
    agent = api.platform.agent
    assert isinstance(agent, FakeAgent)

    def behave(i: AgentInput) -> AgentResult:
        return AgentResult(
            records=[
                r.model_copy(update={"read_through_seq": i.run.read_through_seq})
                for r in held
                if r.author == "agent" and r.written_at == i.run.clock_now
            ]
        )

    agent.behave = behave
    for to in (datetime(2026, 2, 25, tzinfo=UTC), datetime(2026, 6, 1, tzinfo=UTC)):
        _move(api, sample, to)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    with transaction(api.platform.pool) as conn:
        history = store.status_history(conn, charge_id=_id(sample, "chg-l-1002"))
    rows = [
        (row.changed_at.date().isoformat(), row.status.bucket)  # pyright: ignore[reportAttributeAccessIssue]
        for row in history
    ]
    assert rows == [("2026-02-24", Bucket.EVIDENCE_COMPLETE)]
    assert not any(row.status.flagged for row in history)


def test_an_accepted_over_limit_problem_takes_the_amount_over_from_the_problem(api: Api) -> None:
    """Issue 83: the server fills the accepted amount from the current problem and ignores
    the client's."""
    checks = _checks(api)
    checks.grant_problems = [
        Problem(check="budget", problem="over_limit", text="Over.", amount_cents=5000)
    ]
    sample = _sample(api)

    def accept(reason: dict[str, str]) -> Any:
        response = api.client.post(
            f"/grants/{sample.grant.id}/records",
            json={
                "data": {
                    "kind": "accepted_reason",
                    "reason": reason,
                    "note": "The sponsor approved the overspend.",
                    "amount_cents": 1,
                }
            },
            headers=api.headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["data"]["amount_cents"]

    assert accept({"check": "budget", "problem": "over_limit"}) == 5000
    assert accept({"check": "budget", "problem": "something_else"}) is None


def test_accepting_a_notes_offer_raises_its_limit_and_isnt_a_note_of_its_own(api: Api) -> None:
    """Accepting the offer as "this and similar charges" on a larger charge raises the
    original note's amount limit (the checks' note_limit); the acceptance isn't listed as a
    second reusable note."""
    sample = _sample(api)
    l1001, l1002 = _id(sample, "chg-l-1001"), _id(sample, "chg-l-1002")

    def accept(charge_id: str, **extra: object) -> str:
        response = api.client.post(
            f"/grants/{sample.grant.id}/records",
            json={
                "data": {
                    "kind": "accepted_reason",
                    "charge_id": charge_id,
                    "reason": {"check": "fake", "problem": "evidence_complete"},
                    "note": "Lab supplies from this vendor are standard.",
                    "reusable": True,
                    **extra,
                }
            },
            headers=api.headers,
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    note_id = accept(l1001)
    accept(l1002, reuses_id=note_id)
    [view] = _get(api, f"/grants/{sample.grant.id}")["reusable_notes"]
    assert view["note"]["id"] == note_id and view["charge"]["id"] == l1001
    assert view["amount_limit_cents"] == 218000  # L-1002's amount, above L-1001's 124000


class _BenefitChecks(FakeChecks):
    """L-1001 is a salary line that Needs a human; L-1002 is a benefit charge whose only
    open problem is that it waits on L-1001 (or, with `also_missing`, also lacks an item)."""

    salary_id = ""
    benefit_id = ""
    also_missing = False

    def run_checks(self, checks_input: ChecksInput, /) -> ChecksOutput:
        from app.checks.benefits import BENEFIT_RATE, WAITS_ON_SALARY
        from app.contracts.checks import ChargeStatus, ChecklistEntry, ItemSource, Reason

        out = super().run_checks(checks_input)
        statuses = []
        for st in out.charges:
            if st.charge_id == self.salary_id:
                st = st.model_copy(
                    update={
                        "bucket": Bucket.NEEDS_HUMAN,
                        "flagged": True,
                        "reasons": (
                            Reason(check="fake", problem="x", text="?", bucket=Bucket.NEEDS_HUMAN),
                        ),
                    }
                )
            elif st.charge_id == self.benefit_id:
                # As the real checks give it: Missing evidence, unflagged, under the
                # checklist's Benefit rate item.
                reasons = [
                    Reason(
                        check="checklist",
                        problem=WAITS_ON_SALARY,
                        text="Waits on its salary line.",
                        bucket=Bucket.MISSING_EVIDENCE,
                    )
                ]
                if self.also_missing:
                    reasons.append(
                        Reason(
                            check="fake",
                            problem="missing",
                            text="Missing.",
                            bucket=Bucket.MISSING_EVIDENCE,
                        )
                    )
                st = ChargeStatus.model_validate(
                    st.model_dump()
                    | {
                        "bucket": Bucket.MISSING_EVIDENCE,
                        "flagged": self.also_missing,
                        "reasons": tuple(r.model_dump() for r in reasons),
                        "checklist": (
                            ChecklistEntry(
                                default_item=BENEFIT_RATE,
                                added_by=ItemSource.DEFAULT,
                                needed="Benefit rate",
                                filled=False,
                                charge_ids=(self.salary_id,),
                            ).model_dump(),
                        ),
                    }
                )
            statuses.append(st)
        return out.model_copy(update={"charges": tuple(statuses)})


def _benefit_rows(api: Api, also_missing: bool) -> tuple[list[Any], _BenefitChecks]:
    checks = _BenefitChecks()
    api.platform.checks = checks
    sample = sample_into_db(api.platform, api.user_id, APRIL_10)
    checks.salary_id = _id(sample, "chg-l-1001")
    checks.benefit_id = _id(sample, "chg-l-1002")
    checks.also_missing = also_missing
    with transaction(api.platform.pool) as conn:
        recheck_grant(conn, checks, sample.grant, APRIL_10, Trigger(kind=TriggerKind.CLOCK))
    rows = _get(api, f"/grants/{sample.grant.id}/problems")["rows"]
    return [r for r in rows if r["kind"] == "charge"], checks


def test_a_benefit_waiting_only_on_its_salary_line_shows_with_that_row(api: Api) -> None:
    """Ruling 62."""
    rows, checks = _benefit_rows(api, also_missing=False)
    assert [r["charge"]["id"] for r in rows] == [checks.salary_id]
    assert rows[0]["waiting_charge_ids"] == [checks.benefit_id]


def test_a_benefit_with_another_problem_keeps_its_own_row(api: Api) -> None:
    rows, checks = _benefit_rows(api, also_missing=True)
    ids = [r["charge"]["id"] for r in rows]
    assert checks.benefit_id in ids and checks.salary_id in ids
    assert all(r["waiting_charge_ids"] == [] for r in rows)


def test_an_earlier_signed_report_stays_on_file_and_is_checked(api: Api) -> None:
    """Decision 0022: signing again leaves the earlier signed report on file, unchanged and
    fetchable through its own sign-off; a stored report that doesn't match its checksum
    isn't served."""
    sample = _sample(api)
    path = f"/grants/{sample.grant.id}/records"
    with transaction(api.platform.pool) as conn:
        conn.execute(
            "update public.agent_runs set status = 'done' where grant_id = %s", (sample.grant.id,)
        )

    def sign(note: str) -> Any:
        response = api.client.post(
            path, json={"data": {"kind": "sign_off", "note": note}}, headers=api.headers
        )
        assert response.status_code == 201, response.text
        return response.json()

    first = sign("First.")
    first_pdf = api.client.get(f"/records/{first['id']}/report", headers=api.headers).content
    second = sign("Again.")
    assert _get(api, f"/grants/{sample.grant.id}")["sign_off"]["sign_off"]["id"] == second["id"]
    again = api.client.get(f"/records/{first['id']}/report", headers=api.headers)
    assert again.status_code == 200 and again.content == first_pdf
    storage = api.platform.storage
    assert isinstance(storage, FakeStorage)
    storage.objects[first["data"]["report_path"]] = (b"%PDF changed", "application/pdf")
    tampered = api.client.get(f"/records/{first['id']}/report", headers=api.headers)
    assert tampered.status_code == 409
    assert b"%PDF changed" not in tampered.content
    assert tampered.json()["detail"].startswith("The stored report doesn't match the checksum")


def test_the_grant_page_says_why_sign_off_cant_be_done_now(api: Api) -> None:
    """Ruling 72: while a run is queued or running, the sign-off state carries the same
    words the sign-off route refuses with; once the agent is done, none."""
    sample = _sample(api)
    path = f"/grants/{sample.grant.id}/records"
    with transaction(api.platform.pool) as conn:
        from app.db.jobs import queue_run

        queue_run(conn, sample.grant, Trigger(kind=TriggerKind.CLOCK), APRIL_10)
    reason = _get(api, f"/grants/{sample.grant.id}")["sign_off"]["unavailable_reason"]
    refused = api.client.post(
        path, json={"data": {"kind": "sign_off", "note": "Done."}}, headers=api.headers
    )
    assert refused.status_code == 422 and refused.json()["detail"] == [reason]
    with transaction(api.platform.pool) as conn:
        conn.execute(
            "update public.agent_runs set status = 'done' where grant_id = %s", (sample.grant.id,)
        )
    assert _get(api, f"/grants/{sample.grant.id}")["sign_off"]["unavailable_reason"] is None


def test_the_charge_page_names_every_file_its_records_cite(api: Api) -> None:
    """Issue 275: a file an answer's quote cites is in the charge page's files, not only
    the links' files."""
    sample = _sample(api)
    l1001 = _id(sample, "chg-l-1001")
    letter = _id(sample, "file-award-letter")
    original = next(r for r in sample.records if r.id.startswith("rec-allowable-l-1001"))
    assert isinstance(original.data, Judgment)
    quote = original.data.quotes[0].model_copy(update={"file_id": letter})
    answer = original.model_copy(
        update={
            "id": str(uuid.uuid4()),
            "replaces_id": original.id,
            "stored_seq": None,
            "data": original.data.model_copy(update={"quotes": (quote,)}),
        }
    )
    with transaction(api.platform.pool) as conn:
        store.insert_records(conn, [answer])
    detail = _get(api, f"/charges/{l1001}")
    assert letter in detail["files"]
    assert detail["files"][letter]["name"] == "award_letter.txt"


def _agent_record(sample: SampleGrant, data: dict[str, Any], at: datetime) -> Record:
    return Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": sample.grant.workspace_id,
            "grant_id": sample.grant.id,
            "author": "agent",
            "written_at": at,
            "read_through_seq": 1,
            "data": data,
        }
    )


def _store(api: Api, *records: Record) -> None:
    with transaction(api.platform.pool) as conn:
        store.insert_records(conn, list(records))


def test_a_waiting_duplicate_mark_names_both_its_files(api: Api) -> None:
    """Highlight 10: the likely duplicate. A waiting duplicate mark on L-1001's invoice
    names its copy and its original on the charge page."""
    sample = _sample(api)
    invoice, statement = _id(sample, "file-invoice-1001"), _id(sample, "file-sequencing-statement")
    mark = _agent_record(
        sample,
        {"kind": "duplicate", "copy_file_id": invoice, "original_file_id": statement},
        APRIL_10,
    )
    _store(api, mark)
    detail = _get(api, f"/charges/{_id(sample, 'chg-l-1001')}")
    assert [w["record"]["id"] for w in detail["waiting"]] == [mark.id]
    assert {invoice, statement} <= set(detail["files"])


def test_a_waiting_suggestion_names_the_file_of_the_link_it_replaces(api: Api) -> None:
    """An agent's link always has a part (the contract refuses one without), so a link with
    no part is the accountant's, which never waits. Its file is its target's, as the link
    view shows it, and it stays named while an agent's link waits to replace it."""
    sample = _sample(api)
    l1001 = _id(sample, "chg-l-1001")
    statement = _id(sample, "file-sequencing-statement")
    theirs = Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": sample.grant.workspace_id,
            "grant_id": sample.grant.id,
            "author": "user",
            "author_user_id": api.user_id,
            "written_at": APRIL_10,
            "data": {
                "kind": "link",
                "charge_id": l1001,
                "record_id": _id(sample, "rec-bill-seq-0207"),
                "amount_cents": 124000,
            },
        }
    )
    quote = next(r for r in sample.records if r.id.startswith("rec-allowable-l-1001"))
    assert isinstance(quote.data, Judgment)
    mine = _agent_record(
        sample,
        {
            "kind": "link",
            "charge_id": l1001,
            "record_id": _id(sample, "rec-bill-inv-1001"),
            "amount_cents": 124000,
            "part": quote.data.quotes[0].model_dump(mode="json"),
        },
        APRIL_10,
    ).model_copy(update={"replaces_id": theirs.id})
    _store(api, theirs, mine)
    detail = _get(api, f"/charges/{l1001}")
    assert mine.id in [w["record"]["id"] for w in detail["waiting"]]
    assert statement in detail["files"]


def test_a_file_from_another_grant_or_not_yet_arrived_stays_out(api: Api) -> None:
    march = datetime(2026, 3, 1, tzinfo=UTC)
    sample = _sample(api, march)  # the extension notice arrives on April 9
    other = sample_into_db(api.platform, api.user_id, march)
    notice = _id(sample, "file-extension-notice")
    elsewhere = _id(other, "file-invoice-1001")
    invoice = _id(sample, "file-invoice-1001")
    _store(
        api,
        _agent_record(
            sample,
            {"kind": "duplicate", "copy_file_id": invoice, "original_file_id": notice},
            march,
        ),
        _agent_record(
            sample,
            {"kind": "duplicate", "copy_file_id": invoice, "original_file_id": elsewhere},
            march,
        ),
    )
    files = _get(api, f"/charges/{_id(sample, 'chg-l-1001')}")["files"]
    assert invoice in files
    assert notice not in files and elsewhere not in files


def test_a_suggestion_moving_the_accountants_link_names_that_links_file(api: Api) -> None:
    """The no-part branch: the accountant linked L-1002 to the sequencing statement's bill
    with no part; an agent's link waiting to move it to L-1001 is on L-1001's page, and
    names the statement through the link it would replace."""
    sample = _sample(api)
    l1001, l1002 = _id(sample, "chg-l-1001"), _id(sample, "chg-l-1002")
    statement = _id(sample, "file-sequencing-statement")
    theirs = Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": sample.grant.workspace_id,
            "grant_id": sample.grant.id,
            "author": "user",
            "author_user_id": api.user_id,
            "written_at": APRIL_10,
            "data": {
                "kind": "link",
                "charge_id": l1002,
                "record_id": _id(sample, "rec-bill-seq-0207"),
                "amount_cents": 218000,
            },
        }
    )
    quote = next(r for r in sample.records if r.id.startswith("rec-allowable-l-1001"))
    assert isinstance(quote.data, Judgment)
    mine = _agent_record(
        sample,
        {
            "kind": "link",
            "charge_id": l1001,
            "record_id": _id(sample, "rec-bill-inv-1001"),
            "amount_cents": 124000,
            "part": quote.data.quotes[0].model_dump(mode="json"),
        },
        APRIL_10,
    ).model_copy(update={"replaces_id": theirs.id})
    _store(api, theirs, mine)
    detail = _get(api, f"/charges/{l1001}")
    assert mine.id in [w["record"]["id"] for w in detail["waiting"]]
    assert statement in detail["files"]
