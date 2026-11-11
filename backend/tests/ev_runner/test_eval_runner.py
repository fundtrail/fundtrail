"""The eval runner (eval/run.py), with a fake model: no paid calls (ruling 70).

The scoring, the reading of the agent's records, the spend cap and the guards are checked on
their own; then every case is played through the app's ordinary paths against a throwaway
database on the TEST_DATABASE_URL server.
"""

import importlib.util
import json
import os
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from app.samples.pack import DATA_DIR

RUN_PY = DATA_DIR.parent / "eval" / "run.py"


def _runner() -> ModuleType:
    name = "eval_runner_under_test"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, RUN_PY)
    assert spec is not None and spec.loader is not None, f"can't load {RUN_PY}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ev = _runner()


def _key(**parts: Any) -> dict[str, Any]:
    key: dict[str, Any] = {"records": [], "links": [], "budget_lines": [], "answers": []}
    key.update(parts)
    return key


def _score(key: dict[str, Any], got: Any) -> Any:
    out = ev.CaseScore(case="c")
    ev.score_agent(key, got, out)
    return out


# Scoring.


def test_a_link_with_the_wrong_amount_is_missing_and_wrong() -> None:
    key = _key(links=[{"file": "memo.eml", "line_id": "L-1", "amount_cents": -45000}])
    out = _score(key, ev.Got(links=[ev.GotLink("memo.eml", "L-1", 45000)]))
    assert out.links.right == 0
    assert out.links.missing == ["link memo.eml -> L-1 for -45000"]
    assert out.links.wrong == ["link memo.eml -> L-1 for 45000"]


def test_a_link_to_another_line_or_from_another_file_is_wrong() -> None:
    key = _key(links=[{"file": "invoice.txt", "line_id": "L-1", "amount_cents": 100}])
    got = ev.Got(links=[ev.GotLink("invoice.txt", "L-2", 100), ev.GotLink("other.txt", "L-1", 100)])
    out = _score(key, got)
    assert (out.links.right, len(out.links.missing), len(out.links.wrong)) == (0, 1, 2)


def test_records_compare_listed_fields_ignoring_case_and_spaces() -> None:
    key = _key(
        records=[
            {"kind": "bill", "file": "a.txt", "fields": {"total": "120000", "vendor": "Ex  Co."}},
            {"kind": "person", "file": "letter.txt", "fields": {"name": "Reese Mockup"}},
        ]
    )
    got = ev.Got(
        records=[
            ev.GotRecord("bill", "a.txt", {"total": "120000", "vendor": "ex co.", "dated": "x"}),
            ev.GotRecord("person", "letter.txt", {"name": "reese mockup"}),
            ev.GotRecord("other_term", "letter.txt", {"text": "leave"}),
        ]
    )
    out = _score(key, got)
    assert (out.records.right, len(out.records.missing), len(out.records.wrong)) == (2, 0, 1)


def test_the_standard_conditions_mark_compares_as_true_or_false() -> None:
    key = _key(
        records=[
            {
                "kind": "other_term",
                "file": "award_letter.txt",
                "fields": {"standard_conditions": "true", "dated": "2026-01-06"},
            }
        ]
    )
    mark = ev.norm(True)
    got = ev.GotRecord(
        "other_term", "award_letter.txt", {"standard_conditions": mark, "dated": "2026-01-06"}
    )
    assert _score(key, ev.Got(records=[got])).records.right == 1
    unmarked = ev.GotRecord(
        "other_term",
        "award_letter.txt",
        {"standard_conditions": ev.norm(False), "dated": "2026-01-06"},
    )
    assert _score(key, ev.Got(records=[unmarked])).records.right == 0


def test_a_record_with_a_different_field_or_file_or_kind_is_wrong() -> None:
    key = _key(records=[{"kind": "bill", "file": "a.txt", "fields": {"total": "120000"}}])
    for got in (
        ev.GotRecord("bill", "a.txt", {"total": "12000"}),
        ev.GotRecord("bill", "b.txt", {"total": "120000"}),
        ev.GotRecord("note", "a.txt", {"total": "120000"}),
        ev.GotRecord("bill", "a.txt", {}),
    ):
        out = _score(key, ev.Got(records=[got]))
        assert (out.records.right, len(out.records.missing), len(out.records.wrong)) == (0, 1, 1)


def test_a_budget_line_with_another_name_is_wrong() -> None:
    key = _key(budget_lines=[{"line_id": "L-1", "budget_line": "Materials and Supplies"}])
    out = _score(key, ev.Got(budget_lines=[ev.GotBudget("L-1", "Other")]))
    assert (out.budget_lines.right, len(out.budget_lines.missing)) == (0, 1)
    assert out.budget_lines.wrong == ["budget line 'Other' for L-1"]
    out = _score(key, ev.Got(budget_lines=[ev.GotBudget("L-1", "materials and  supplies")]))
    assert out.budget_lines.right == 1


def test_an_answer_about_another_file_is_wrong() -> None:
    key = _key(
        answers=[
            {"line_id": "L-1", "question": "covers", "about_file": "a.eml", "answer": "supports"}
        ]
    )
    out = _score(key, ev.Got(answers=[ev.GotAnswer("L-1", "covers", "b.eml", "supports")]))
    assert (out.answers.right, len(out.answers.missing), len(out.answers.wrong)) == (0, 1, 1)
    out = _score(key, ev.Got(answers=[ev.GotAnswer("L-1", "covers", "a.eml", "supports")]))
    assert out.answers.right == 1


def test_one_agent_item_matches_at_most_one_expected_item() -> None:
    key = _key(
        links=[
            {"file": "a.txt", "line_id": "L-1", "amount_cents": 1},
            {"file": "a.txt", "line_id": "L-1", "amount_cents": 1},
        ]
    )
    out = _score(key, ev.Got(links=[ev.GotLink("a.txt", "L-1", 1)]))
    assert (out.links.right, len(out.links.missing), len(out.links.wrong)) == (1, 1, 0)


def test_a_loose_expected_item_doesnt_take_what_a_strict_one_needs() -> None:
    key = _key(
        records=[
            {"kind": "note", "file": "a.txt", "fields": {}},
            {"kind": "note", "file": "a.txt", "fields": {"label": "salary"}},
        ]
    )
    got = ev.Got(
        records=[
            ev.GotRecord("note", "a.txt", {"label": "salary"}),
            ev.GotRecord("note", "a.txt", {"label": "split"}),
        ]
    )
    out = _score(key, got)
    assert (out.records.right, len(out.records.missing), len(out.records.wrong)) == (2, 0, 0)


def test_answers_count_false_clears_and_unsure_on_their_own() -> None:
    key = _key(
        answers=[
            {"line_id": "L-1", "question": "allowable", "answer": "contradicts"},
            {"line_id": "L-2", "question": "allowable", "answer": "supports"},
        ]
    )
    got = ev.Got(
        answers=[
            ev.GotAnswer("L-1", "allowable", None, "supports"),
            ev.GotAnswer("L-2", "allowable", None, "unsure"),
        ]
    )
    out = _score(key, got)
    assert out.answers.right == 0
    assert len(out.answers.missing) == 2 and len(out.answers.wrong) == 2
    assert len(out.agent_false_clears) == 1 and len(out.unsure) == 1


def test_a_checklist_item_matches_by_charge_amount_and_cited_rate() -> None:
    from decimal import Decimal

    item = {
        "line_id": "L-5201",
        "needed": "Per diem",
        "file": "per_diem_rates.txt",
        "amount_cents": 50000,
        "rate": {"quantity": "5", "rate": "100.00"},
    }
    got = ev.Got(
        checklist_items=[
            ev.GotItem(
                "L-5201",
                "5 days of per diem",
                50000,
                "per_diem_rates.txt",
                Decimal("5"),
                Decimal("100"),
            ),
            ev.GotItem(
                "L-5201", "Per diem", 50000, "expense_report.txt", Decimal("5"), Decimal("100")
            ),
        ]
    )
    out = ev.CaseScore(case="c")
    ev.score_agent(_key(checklist_items=[item]), got, out)
    assert out.checklist_items.right == 1
    assert len(out.checklist_items.wrong) == 1 and not out.checklist_items.missing


def test_checklist_items_are_unscored_when_the_key_has_none() -> None:
    from decimal import Decimal

    got = ev.Got(checklist_items=[ev.GotItem("L-1", "x", None, None, None, Decimal("1"))])
    out = ev.CaseScore(case="c")
    ev.score_agent(_key(), got, out)
    assert out.unscored_parts == ["checklist_items"]
    assert not out.checklist_items.wrong


def test_an_item_the_key_leaves_unscored_is_neither_right_nor_wrong() -> None:
    key = _key(not_scored=[{"part": "budget_lines", "line_id": "L-7101"}])
    got = ev.Got(
        budget_lines=[ev.GotBudget("L-7101", "Stipends"), ev.GotBudget("L-7102", "Stipends")]
    )
    out = ev.CaseScore(case="c")
    ev.score_agent(key, got, out)
    assert out.not_scored == ["budget line 'Stipends' for L-7101"]
    assert out.budget_lines.wrong == ["budget line 'Stipends' for L-7102"]


def test_one_answer_is_counted_once_as_unsure() -> None:
    key = _key(
        answers=[
            {"line_id": "L-1", "question": "allowable", "answer": "supports"},
            {"line_id": "L-1", "question": "allowable", "answer": "supports"},
        ]
    )
    out = _score(key, ev.Got(answers=[ev.GotAnswer("L-1", "allowable", None, "unsure")]))
    assert len(out.unsure) == 1


def test_buckets_are_right_wrong_or_missing_and_false_clears_counted() -> None:
    out = ev.CaseScore(case="c")
    want = {"line_id": "L-1", "at": "2026-03-09T12:00:00Z", "bucket": "missing_evidence"}
    ev.score_bucket(want, "missing_evidence", out)
    ev.score_bucket(want, "evidence_complete", out)
    ev.score_bucket(want, None, out)
    assert out.buckets.right == 1
    assert len(out.buckets.wrong) == 1 and len(out.false_clears) == 1
    assert len(out.buckets.missing) == 1


def test_a_fully_reversed_charge_reads_as_reversed() -> None:
    from app.contracts.checks import Bucket

    charges = [SimpleNamespace(id="c1", ledger_line_id="L-1")]

    def status(reversed: bool) -> Any:
        charge = SimpleNamespace(
            charge_id="c1", bucket=Bucket.MISSING_EVIDENCE, reasons=(), reversed=reversed
        )
        return SimpleNamespace(charges=[charge])

    assert ev.bucket_of(status(True), charges, "L-1") == ("reversed", "")
    assert ev.bucket_of(status(False), charges, "L-1") == ("missing_evidence", "")
    assert ev.bucket_of(status(False), charges, "L-9") == (None, "")


# Reading what the agent left.


def test_the_agent_records_are_read_as_the_key_compares_them() -> None:
    """The golden sample's records (contracts.md section 15), the agent's and the
    accountant's: only the agent's current ones count, each with its case file and charge."""
    from app.contracts.fixtures import load_sample_grant
    from app.contracts.records import Author

    sample = load_sample_grant()
    link = next(r for r in sample.records if r.id == "rec-link-l-1001")
    users_link = link.model_copy(
        update={"id": "rec-user-link", "author": Author.USER, "author_user_id": "u1"}
    )
    records = [*sample.records, users_link]
    got = ev.what_the_agent_left(records, sample.files, sample.charges, lambda f: f.name)
    assert got.links == [
        ev.GotLink("invoice_1001.txt", "L-1001", 124000),
        ev.GotLink("sequencing_statement.eml", "L-1002", 218000),
    ]
    assert got.budget_lines == [
        ev.GotBudget("L-1001", "Materials and Supplies"),
        ev.GotBudget("L-1002", "Other"),
    ]
    assert got.answers == [
        ev.GotAnswer("L-1001", "allowable", None, "supports"),
        ev.GotAnswer("L-1002", "allowable", None, "supports"),
    ]
    bills = [r for r in got.records if r.kind == "bill"]
    assert [(b.file, b.fields["total"]) for b in bills] == [
        ("invoice_1001.txt", "124000"),
        ("sequencing_statement.eml", "218000"),
    ]
    assert not any(r.kind == "confirmation" for r in got.records)
    # The period, four budget lines, three people, the approval rule, the notice, two bills
    # and the extension's period: 13, with the accountant's confirmations left out.
    assert len(got.records) == 13


def test_a_file_is_named_by_its_bytes_and_an_attachment_by_its_email() -> None:
    files = [
        SimpleNamespace(id="f1", parent_id=None, sha256="aaa", name="Invoice 20417.eml"),
        SimpleNamespace(id="f2", parent_id="f1", sha256="bbb", name="memo.pdf"),
        SimpleNamespace(id="f3", parent_id=None, sha256="ccc", name="user_upload.txt"),
    ]
    name = ev.case_namer(files, {"aaa": "credit_memo_20417.eml"})
    assert [name(f) for f in files] == [
        "credit_memo_20417.eml",
        "credit_memo_20417.eml",
        "user_upload.txt",
    ]


# The spend cap.


def _request(max_tokens: int = 1000) -> Any:
    return SimpleNamespace(max_tokens=max_tokens, system=[], tools=[], messages=[])


def test_the_cap_refuses_a_call_before_it_could_pass() -> None:
    meter = ev.Meter(ev.fake_model, cap_usd=0.30)
    calls = 0
    with pytest.raises(ev.CapReached):
        for _ in range(1000):
            meter(_request())
            calls += 1
    # Each fake call costs $0.006; its worst case is 1,000 output tokens ($0.02) and its input.
    assert meter.stopped and calls == meter.used.calls
    assert meter.used.usd <= meter.cap_usd
    with pytest.raises(ev.CapReached):
        meter(_request())
    assert meter.used.calls == calls


def test_the_cap_refuses_a_call_dearer_than_any_before_it() -> None:
    """A turn retried at 128,000 output tokens could cost $2.56 in output alone: it's
    refused on a $1 cap before it runs, however cheap the calls before it were."""
    expensive: list[int] = []

    def model(request: Any) -> Any:
        message = ev.fake_model(request)
        if request.max_tokens > 1000:
            expensive.append(request.max_tokens)
            message.usage.output_tokens = request.max_tokens
        return message

    meter = ev.Meter(model, cap_usd=1.00)
    for _ in range(4):
        meter(_request())
    with pytest.raises(ev.CapReached):
        meter(_request(128000))
    assert not expensive
    assert meter.used.usd <= 1.00


def test_the_cap_counts_a_calls_input() -> None:
    """A request with no output to speak of but 400,000 characters of input counts as
    200,000 tokens, $1.00 at the cache-write price: refused on a $0.80 cap. (Counted at 3
    characters a token, it would be $0.67, and let through.)"""
    meter = ev.Meter(ev.fake_model, cap_usd=0.80)
    big = SimpleNamespace(
        max_tokens=0, system=[], tools=[], messages=[{"role": "user", "content": "x" * 400_000}]
    )
    with pytest.raises(ev.CapReached):
        meter(big)
    assert meter.used.calls == 0


def test_the_cap_counts_the_last_calls_input() -> None:
    """A small request after a call that read 300,000 tokens is reserved at that size."""

    def model(request: Any) -> Any:
        message = ev.fake_model(request)
        message.usage.input_tokens = 300_000
        message.usage.output_tokens = 0
        return message

    meter = ev.Meter(model, cap_usd=2.00)
    meter(_request(0))  # $1.20 spent
    with pytest.raises(ev.CapReached):
        meter(_request(0))  # 300,000 tokens at $5 per million: $1.50 more could pass $2.00
    assert meter.used.calls == 1


# The guards.


def test_only_a_local_database_server_is_used() -> None:
    for url in (
        "postgresql://postgres@127.0.0.1:5432/postgres",
        "postgresql://postgres:postgres@localhost:5432/postgres",
        "postgresql://postgres@[::1]/postgres",
        "host=/tmp dbname=postgres",
        "postgresql://localhost/postgres?hostaddr=127.0.0.1",
    ):
        ev.check_local(url, environ={})
    for url in (
        "postgresql://postgres:secret@db.project.supabase.example:5432/postgres",
        "postgresql://postgres@127.0.0.1,db.example.org/postgres",
        "host=localhost hostaddr=203.0.113.5 dbname=postgres",
        "postgresql://localhost/postgres?hostaddr=203.0.113.5",
        "service=prod",
    ):
        with pytest.raises(ev.NotLocal):
            ev.check_local(url, environ={})
    # An empty host is filled from PGHOST, and PGHOSTADDR and PGSERVICE count too.
    ev.check_local("postgresql:///postgres", environ={})
    ev.check_local("dbname=postgres", environ={"PGHOST": "/tmp"})
    for env in ({"PGHOST": "203.0.113.5"}, {"PGHOSTADDR": "203.0.113.5"}, {"PGSERVICE": "x"}):
        with pytest.raises(ev.NotLocal):
            ev.check_local("postgresql:///postgres", environ=env)


def test_the_hosted_and_mail_settings_are_dropped_while_it_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ev.HOSTED_SETTINGS:
        monkeypatch.setenv(name, "set")
    assert {"GOOGLE_TOKEN_FILE", "FUNDTRAIL_MAILBOX", "DATABASE_URL"} <= set(ev.HOSTED_SETTINGS)
    with ev.without_hosted_settings():
        assert not any(name in os.environ for name in ev.HOSTED_SETTINGS)
    assert all(os.environ.get(name) == "set" for name in ev.HOSTED_SETTINGS)


# Every case through the app.


def _server() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


def _key_of(case: str) -> dict[str, Any]:
    return json.loads((ev.CASES / case / "answer_key.json").read_text())


def test_every_case_plays_through_the_app_with_a_fake_model() -> None:
    before = dict(os.environ)
    run = ev.run_eval(_server(), None, 100.0, ev.fake_model)
    assert dict(os.environ) == before
    cases = sorted(p.name for p in ev.CASES.iterdir() if (p / "answer_key.json").is_file())
    assert [c.case for c in run.cases] == cases
    assert not run.stopped and run.base_url is None
    for c in run.cases:
        key = _key_of(c.case)
        for part in ("links", "budget_lines", "answers", "records", "checklist_items"):
            t = getattr(c, part)
            assert t.right + len(t.missing) == len(key.get(part, [])), (c.case, part)
        assert ("checklist_items" in c.unscored_parts) == ("checklist_items" not in key)
        # The fake model writes nothing, so no term is confirmed, and every charge is in
        # Needs a human at every time the key names, read at that time, never missing.
        in_time_order = sorted(key["buckets"], key=lambda b: b["at"])
        assert c.bucket_values == [
            f"{b['line_id']} at {b['at']}: needs_human" for b in in_time_order
        ], c.case
        assert c.usage.calls > 0
        assert c.steps_left_for_user  # nothing to confirm
    assert all(c.links.right == 0 and not c.links.wrong for c in run.cases)
    assert run.usage.calls == sum(c.usage.calls for c in run.cases)
    assert run.usage.usd == pytest.approx(run.usage.calls * 0.006)
    text = ev.report(run)
    assert "## All cases" in text and "estimated $" in text and "calls through" not in text


class TimeChecks:
    """The real checks, except that a charge is Evidence complete only at exactly the times
    the keys name for it, and Needs a human at any other: a bucket read at the wrong time
    shows."""

    def __init__(self) -> None:
        from app.db.ports import ModuleChecks

        self.real = ModuleChecks()
        self.times = {
            (b["line_id"], ev._time(b["at"]))  # pyright: ignore[reportPrivateUsage]
            for d in ev.CASES.iterdir()
            if (d / "answer_key.json").is_file()
            for b in _key_of(d.name)["buckets"]
        }

    def run_checks(self, checks_input: Any) -> Any:
        from app.contracts.checks import Bucket, ChargeStatus, Reason

        out = self.real.run_checks(checks_input)
        line = {c.id: c.ledger_line_id for c in checks_input.charges}

        def at_key_time(s: Any) -> Any:
            on_time = (line[s.charge_id], checks_input.now) in self.times
            bucket = Bucket.EVIDENCE_COMPLETE if on_time else Bucket.NEEDS_HUMAN
            reason = Reason(check="eval_time", problem=bucket.value, text="test", bucket=bucket)
            data = s.model_dump()
            data.update(bucket=bucket, reasons=[reason.model_dump()], flagged=not on_time)
            return ChargeStatus.model_validate(data)

        charges = tuple(at_key_time(s) for s in out.charges)
        return out.model_copy(update={"charges": charges})

    def default_items(self, charge: Any, records: Any) -> Any:
        return self.real.default_items(charge, records)

    def account_categories(self, account: str) -> Any:
        return self.real.account_categories(account)


def test_each_bucket_is_read_at_the_time_the_key_names() -> None:
    run = ev.run_eval(
        _server(), ["credit-memo-spaced-dash"], 100.0, ev.fake_model, checks=TimeChecks()
    )
    [case] = run.cases
    assert case.bucket_values and all(
        v.endswith(": evidence_complete") for v in case.bucket_values
    ), case.bucket_values


def test_values_not_found_in_their_file_are_counted() -> None:
    from app.contracts.fixtures import load_sample_grant
    from app.contracts.records import Match

    sample = load_sample_grant()
    records = []
    for r in sample.records:
        if r.id == "rec-bill-inv-1001":
            total = r.data.total  # pyright: ignore[reportAttributeAccessIssue]
            assert total.citation is not None
            citation = total.citation.model_copy(update={"match": Match.NOT_FOUND})
            data = r.data.model_copy(
                update={"total": total.model_copy(update={"citation": citation})}
            )
            r = r.model_copy(update={"data": data})
        records.append(r)
    got = ev.what_the_agent_left(records, sample.files, sample.charges, lambda f: f.name)
    assert got.values_not_found == 1
    out = _score(_key(), got)
    assert out.values_not_found == 1


def test_a_stray_queued_task_fails_the_eval() -> None:
    from app.db.jobs import app as jobs_app

    with ev.throwaway_database(_server()) as url:
        import psycopg

        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(
                "insert into procrastinate_jobs (queue_name, task_name, status)"
                " values ('agent', 'check_mail_and_drive', 'succeeded')"
            )
        with pytest.raises(RuntimeError, match="check_mail_and_drive"):
            ev.drain(url)
    # The jobs app keeps its periodic tasks for the app's own worker.
    assert jobs_app.periodic_registry.periodic_tasks


def test_the_cap_stops_the_eval_before_it_goes_over() -> None:
    run = ev.run_eval(_server(), None, 0.30, ev.fake_model)
    assert run.stopped
    assert run.usage.usd <= 0.30
    assert run.cases[-1].stopped
    assert "stopped at the cap" in ev.report(run)
