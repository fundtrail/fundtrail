"""The screen bodies (#22 as agreed, PR 40's names) over the sample grant (contracts.md
section 15), with the checks faked."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChecksInput, ChecksOutput, Problem
from app.contracts.fixtures import SampleGrant
from app.contracts.records import DefaultItem, Record
from app.contracts.runs import Trigger, TriggerKind
from app.db import store
from app.db.jobs import NORMAL_PRIORITY, THREAD_PRIORITY
from app.db.pool import transaction
from app.db.ports import AgentInput, AgentResult
from app.db.recheck import recheck_grant
from tests.api.conftest import Api
from tests.db.platform_fixtures import FakeAgent, FakeChecks, run_worker_until_idle, sample_into_db

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
    assert detail["sign_off"] == {"state": "not_signed", "sign_off": None, "changes": []}

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


# The clock (decision 0023).


def test_a_real_workspace_clock_cant_move(api: Api) -> None:
    workspace = api.client.post("/workspaces", json={"name": "Lab"}, headers=api.headers).json()
    clock = _get(api, f"/workspaces/{workspace['id']}/clock")
    assert clock["simulated"] is False and clock["next_arrival"] is None
    moved = api.client.post(f"/workspaces/{workspace['id']}/clock", json={}, headers=api.headers)
    assert moved.status_code == 422 and "real date" in moved.json()["detail"][0]


def test_the_clock_names_the_next_arrival_and_only_moves_forward(api: Api) -> None:
    sample = _sample(api, datetime(2025, 11, 13, tzinfo=UTC))
    path = f"/workspaces/{sample.workspace.id}/clock"
    clock = _get(api, path)
    assert clock["simulated"] is True and clock["now"] == "2025-11-13T00:00:00Z"
    assert clock["next_arrival"]["source"] == "ledger" and clock["next_arrival"]["name"] == "L-1001"
    back = api.client.post(path, json={"to": "2025-01-01T00:00:00Z"}, headers=api.headers)
    assert back.status_code == 422 and "forward" in back.json()["detail"][0]
    moved = api.client.post(path, json={}, headers=api.headers).json()
    assert moved["now"] == "2025-11-14T00:00:00Z"
    assert moved["next_arrival"]["source"] == "gmail"
    assert moved["next_arrival"]["name"] == "sequencing_statement.eml"


def test_a_jump_is_replayed_in_arrival_order(api: Api) -> None:
    sample = _sample(api, datetime(2025, 10, 1, tzinfo=UTC))
    path = f"/workspaces/{sample.workspace.id}/clock"
    moved = api.client.post(path, json={"to": "2025-11-20T00:00:00Z"}, headers=api.headers).json()
    assert moved["catching_up"] is True
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
    assert _get(api, path)["catching_up"] is False


def test_a_thread_question_during_a_catch_up_waits_for_it(api: Api) -> None:
    sample = _sample(api, datetime(2025, 11, 13, tzinfo=UTC))
    api.client.post(
        f"/workspaces/{sample.workspace.id}/clock",
        json={"to": "2025-11-20T00:00:00Z"},
        headers=api.headers,
    )
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
    clock = f"/workspaces/{sample.workspace.id}/clock"
    moved = api.client.post(clock, json={}, headers=api.headers).json()
    assert moved["now"] == "2025-11-14T00:00:00Z" and moved["catching_up"] is True

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
    assert _get(api, clock)["catching_up"] is False
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
            "update public.workspaces set clock_now = %s where id = %s",
            (APRIL_10, sample.workspace.id),
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
            records=[r for r in held if r.author == "agent" and r.written_at == i.run.clock_now]
        )

    agent.behave = behave
    moved = api.client.post(
        f"/workspaces/{sample.workspace.id}/clock",
        json={"to": "2026-05-01T00:00:00Z"},
        headers=api.headers,
    )
    assert moved.status_code == 200, moved.text
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
    path = f"/workspaces/{sample.workspace.id}/clock"
    api.client.post(path, json={"to": "2025-12-11T00:00:00Z"}, headers=api.headers)
    with transaction(api.platform.pool) as conn:
        reviews = [r for r in store.list_runs(conn, sample.grant.id) if r.trigger.kind == "clock"]
    assert [r.clock_now.date().isoformat() for r in reviews] == ["2025-12-01"]
    # The extension (end Jan 31, 2027) is confirmed on Apr 10, 2026: its window opens
    # Nov 2, 2026, and a move past it queues a review for the new end date.
    api.client.post(path, json={"to": "2026-11-05T00:00:00Z"}, headers=api.headers)
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
    assert detail["sign_off"] == {"state": "not_signed", "sign_off": None, "changes": []}


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
            records=[r for r in held if r.author == "agent" and r.written_at == i.run.clock_now]
        )

    agent.behave = behave
    clock = f"/workspaces/{sample.workspace.id}/clock"
    for to in ("2026-02-25T00:00:00Z", "2026-06-01T00:00:00Z"):
        moved = api.client.post(clock, json={"to": to}, headers=api.headers)
        assert moved.status_code == 200, moved.text
    run_worker_until_idle(str(api.platform.pool.conninfo))
    with transaction(api.platform.pool) as conn:
        history = store.status_history(conn, charge_id=_id(sample, "chg-l-1002"))
    rows = [
        (row.changed_at.date().isoformat(), row.status.bucket)  # pyright: ignore[reportAttributeAccessIssue]
        for row in history
    ]
    assert rows == [("2026-02-24", Bucket.EVIDENCE_COMPLETE)]
    assert not any(row.status.flagged for row in history)
