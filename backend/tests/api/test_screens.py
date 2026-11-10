"""The screen bodies (#22 as agreed, PR 40's names) over the sample grant (contracts.md
section 15), with the checks faked."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.contracts.checks import Bucket, Problem
from app.contracts.fixtures import SampleGrant
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
    assert detail["budget"]["line"]["data"]["name"]["value"] == "Materials and Supplies"
    [link] = detail["links"]
    assert link["record"]["data"]["kind"] == "bill" and link["file"]["name"] == "invoice_1001.txt"
    assert link["values"] and all(v["confirmed"] and v["how"] == "found" for v in link["values"])
    [answer] = detail["answers"]
    assert answer["judgment"]["data"]["answer"] == "supports" and not answer["out_of_date"]
    assert detail["account_categories"] == ["materials_and_supplies"]
    [entry] = detail["history"]
    assert entry["text"] == "Apr 10, 2026 · time passed · Evidence complete"
    assert [i["kind"] for i in detail["thread"]["items"]] == ["check"]
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
    assert [i["kind"] for i in thread["items"]] == ["check", "message"]
    assert thread["agent"] == "queued"
    with transaction(api.platform.pool) as conn:
        [job] = conn.execute("select priority from procrastinate_jobs").fetchall()
    assert job["priority"] == THREAD_PRIORITY


def test_a_records_thread_follows_its_correction(api: Api) -> None:
    sample = _sample(api)
    old = _id(sample, "rec-person-pi")
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
    items = _get(api, f"/records/{old}/thread")["items"]
    # The award terms' confirmation, the correction, then the message.
    assert [i["kind"] for i in items] == ["decision", "decision", "message"]
    assert items[1]["text"] == "person corrected by the accountant"


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
    state = _get(api, f"/grants/{sample.grant.id}")["sign_off"]
    assert state["state"] == "signed" and state["sign_off"]["id"] == signed.json()["id"]


def test_the_report_route_gives_the_draft(api: Api) -> None:
    sample = _sample(api)
    path = f"/grants/{sample.grant.id}/report"
    assert api.client.get(path, headers=api.headers).status_code == 503

    class Maker:
        def render(self, conn: object, snapshot: object) -> bytes:
            return b"%PDF-1.7 draft"

    api.client.app.state.report_maker = Maker()  # pyright: ignore[reportAttributeAccessIssue, reportFunctionMemberAccess]
    response = api.client.get(path, headers=api.headers)
    assert response.status_code == 200 and response.content == b"%PDF-1.7 draft"
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
    assert moved["next_arrival"]["source"] == "email"
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
    # The charge's first status is stamped on its arrival, with the charge as its trigger.
    assert history[0].changed_at == datetime(2025, 11, 14, tzinfo=UTC)
    assert history[0].trigger.kind == TriggerKind.CHARGE


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
    assert priorities == [NORMAL_PRIORITY, NORMAL_PRIORITY]


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
    assert tries[:3] == [TriggerKind.CHARGE, TriggerKind.CHARGE, TriggerKind.THREAD_MESSAGE]
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
