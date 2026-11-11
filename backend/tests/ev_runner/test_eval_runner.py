"""The eval runner (eval/run.py), with a fake model: no paid calls (ruling 70).

The scoring and the spend cap are checked on their own; then every case is played through
the app's ordinary paths against a throwaway database on the TEST_DATABASE_URL server.
"""

import importlib.util
import json
import os
import sys
from types import ModuleType
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


def test_a_link_with_the_wrong_amount_is_missing_and_wrong() -> None:
    key = _key(
        links=[
            {"file": "invoice.txt", "line_id": "L-1", "amount_cents": 120000},
            {"file": "memo.eml", "line_id": "L-1", "amount_cents": -45000},
        ]
    )
    got = ev.Got(
        links=[ev.GotLink("invoice.txt", "L-1", 120000), ev.GotLink("memo.eml", "L-2", -45000)]
    )
    out = ev.CaseScore(case="c")
    ev.score_agent(key, got, out)
    assert out.links.right == 1
    assert out.links.missing == ["link memo.eml -> L-1 for -45000"]
    assert out.links.wrong == ["link memo.eml -> L-2 for -45000"]


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
    out = ev.CaseScore(case="c")
    ev.score_agent(key, got, out)
    assert (out.records.right, len(out.records.missing), len(out.records.wrong)) == (2, 0, 1)


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
    out = ev.CaseScore(case="c")
    ev.score_agent(key, got, out)
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


def test_buckets_are_right_wrong_or_missing_and_false_clears_counted() -> None:
    out = ev.CaseScore(case="c")
    want = {"line_id": "L-1", "at": "2026-03-09T12:00:00Z", "bucket": "missing_evidence"}
    ev.score_bucket(want, "missing_evidence", out)
    ev.score_bucket(want, "evidence_complete", out)
    ev.score_bucket(want, None, out)
    assert out.buckets.right == 1
    assert len(out.buckets.wrong) == 1 and len(out.false_clears) == 1
    assert len(out.buckets.missing) == 1


def test_the_cap_refuses_a_call_before_it_could_pass() -> None:
    meter = ev.Meter(ev.fake_model, cap_usd=0.30)
    calls = 0
    with pytest.raises(ev.CapReached):
        for _ in range(1000):
            meter(None)
            calls += 1
    # Each fake call costs $0.006; a call is refused once the spend plus $0.25 would pass $0.30.
    assert meter.stopped and calls == meter.used.calls == 9
    assert meter.used.usd <= meter.cap_usd
    with pytest.raises(ev.CapReached):
        meter(None)
    assert meter.used.calls == 9


def test_only_a_local_database_server_is_used() -> None:
    for url in (
        "postgresql://postgres@127.0.0.1:5432/postgres",
        "postgresql://postgres:postgres@localhost:5432/postgres",
        "postgresql://postgres@[::1]/postgres",
        "host=/tmp dbname=postgres",
    ):
        ev.check_local(url)
    for url in (
        "postgresql://postgres:secret@db.project.supabase.example:5432/postgres",
        "postgresql://postgres@127.0.0.1,db.example.org/postgres",
    ):
        with pytest.raises(ev.NotLocal):
            ev.check_local(url)


def test_the_hosted_settings_are_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ev.HOSTED_SETTINGS:
        monkeypatch.setenv(name, "set")
    ev.drop_hosted_settings()
    assert not any(name in os.environ for name in ev.HOSTED_SETTINGS)


def _server() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    return url


def _key_of(case: str) -> dict[str, Any]:
    return json.loads((ev.CASES / case / "answer_key.json").read_text())


def test_every_case_plays_through_the_app_with_a_fake_model() -> None:
    run = ev.run_eval(_server(), None, 100.0, ev.fake_model)
    cases = sorted(p.name for p in ev.CASES.iterdir() if (p / "answer_key.json").is_file())
    assert [c.case for c in run.cases] == cases
    assert not run.stopped
    for c in run.cases:
        key = _key_of(c.case)
        for part in ("links", "budget_lines", "answers", "records", "checklist_items"):
            t = getattr(c, part)
            assert t.right + len(t.missing) == len(key.get(part, [])), (c.case, part)
        assert ("checklist_items" in c.unscored_parts) == ("checklist_items" not in key)
        b = c.buckets
        assert b.right + len(b.missing) + len(b.wrong) == len(key["buckets"]), c.case
        assert c.usage.calls > 0
    # The fake model writes nothing, so nothing the agent should write is there.
    assert all(c.links.right == 0 and not c.links.wrong for c in run.cases)
    assert run.usage.calls == sum(c.usage.calls for c in run.cases)
    assert run.usage.usd == pytest.approx(run.usage.calls * 0.006)
    text = ev.report(run)
    assert "## All cases" in text and "estimated $" in text


def test_the_cap_stops_the_eval_before_it_goes_over() -> None:
    run = ev.run_eval(_server(), None, 0.30, ev.fake_model)
    assert run.stopped
    assert run.usage.usd <= 0.30
    assert run.cases[-1].stopped
    assert "stopped at the cap" in ev.report(run)
