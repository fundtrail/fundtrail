"""Terms read from an award notice that code can use (issue #117).

An approval rule's applies_to has to name the budget line or NSF category, as the notice prints
it, so code's matcher (app.checks.rules_match) can tell which charges it covers. The real model
once wrote the clause's lead-in, "Funds budgeted for Participant Support Costs", which matched
nothing and sent every charge on the grant to the accountant.
"""

from datetime import datetime

from anthropic.types import CitationCharLocation

from app.agent.citations import LabelLine
from app.agent.context import REPEAT_LIMIT, RunContext
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool, tool_definitions
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import ApprovalRule
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs

SAMPLE = load_sample_grant()
AWARD = SAMPLE.document("file-award-letter")
CLAUSE = (
    "Special conditions: Funds budgeted for Participant Support Costs may not be diverted by the "
    "awardee to other categories of expense without the prior written approval of the cognizant "
    "NSF Program Officer, requested through Research.gov."
)
DATED = "Amendment Date: January 10, 2023"


def award_context() -> RunContext:
    inputs = sample_inputs(
        now=datetime.fromisoformat("2023-01-12T15:00:00+00:00"),
        trigger=Trigger(kind=TriggerKind.FILE, id="file-award-letter"),
        records=[],
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    _, error = run_tool(ctx, "open_file", {"file_id": "file-award-letter"})
    assert not error
    return ctx


def label(ctx: RunContext, name: str, value: str, chunk: str) -> None:
    start = AWARD.find(chunk)
    cite = CitationCharLocation(
        type="char_location",
        cited_text=chunk,
        document_index=0,
        start_char_index=start,
        end_char_index=start + len(chunk),
    )
    ctx.labels[name] = LabelLine(name, value, [cite])


def rule(ctx: RunContext, applies_to: str) -> tuple[str, bool]:
    label(ctx, "dated", "January 10, 2023", DATED)
    label(ctx, "applies", applies_to, CLAUSE)
    label(ctx, "approver", "Program Officer", CLAUSE)
    label(ctx, "channel", "Research.gov", CLAUSE)
    values = [
        {"field": "dated", "label": "dated"},
        {"field": "applies_to", "label": "applies"},
        {"field": "approver", "label": "approver"},
        {"field": "channel", "label": "channel"},
    ]
    return run_tool(ctx, "write_term", {"kind": "approval_rule", "values": values})


def test_the_clauses_lead_in_is_refused_with_the_words_to_cite_instead():
    ctx = award_context()
    result, error = rule(ctx, "Funds budgeted for Participant Support Costs")
    assert error and "can't match 'Funds budgeted for Participant Support Costs'" in result
    assert "Participant Support Costs" in result and not ctx.staged


def test_the_budget_lines_own_name_is_saved_with_the_clause_as_its_citation():
    ctx = award_context()
    result, error = rule(ctx, "Participant Support Costs")
    assert not error, result
    data = ctx.staged[-1].record.data
    assert isinstance(data, ApprovalRule)
    assert data.applies_to.value == "Participant Support Costs"
    assert data.applies_to.citation is not None and data.applies_to.citation.passage == CLAUSE


def test_an_nsf_category_name_matches_without_a_budget_line_on_file():
    ctx = award_context()
    result, error = rule(ctx, "Participant Support")
    assert not error, result


def test_a_rule_code_still_cant_match_is_saved_on_the_third_try_with_a_flag_asked_for():
    """Leaving the rule out would turn its check off; saved, it sends every charge to a person."""
    ctx = award_context()
    for _ in range(REPEAT_LIMIT - 1):
        _, error = rule(ctx, "Funds budgeted for Participant Support Costs")
        assert error
    result, error = rule(ctx, "Funds budgeted for Participant Support Costs")
    assert not error and "flag the term" in result


def test_the_guidance_says_to_cite_the_narrowest_words():
    write_term = next(t for t in tool_definitions() if t["name"] == "write_term")
    flat = " ".join(write_term["description"].split())
    assert 'not "Funds budgeted for Participant Support Costs"' in flat


def _line(record_id: str, name: str) -> dict[str, object]:
    passage = "6. Other                                               $60,000"
    start = AWARD.find(passage)
    cite = {
        "file_id": "file-award-letter",
        "passage": passage,
        "location": {
            "type": "char_location",
            "start_char_index": start,
            "end_char_index": start + len(passage),
        },
        "match": "exact",
    }
    return {
        "id": record_id,
        "workspace_id": SAMPLE.workspace.id,
        "grant_id": SAMPLE.grant.id,
        "author": "agent",
        "written_at": "2023-01-12T15:00:00+00:00",
        "data": {
            "kind": "budget_line",
            "dated": {"value": "2023-01-10", "text": "Other", "citation": cite},
            "name": {"value": name, "text": "Other", "citation": cite},
            "amount": {"value": 6000000, "text": "Other", "citation": cite},
            "category": "other_direct_costs_other",
        },
    }


def test_only_budget_lines_in_force_or_waiting_count():
    """PR 127's review: the checks' own matcher, so a rejected line doesn't count."""
    from app.agent.adapter import applies_to_is_matchable
    from app.contracts.records import Record

    line = Record.model_validate(_line("rec-line-field", "Field Work"))
    files = SAMPLE.files
    assert applies_to_is_matchable("Field Work", [line], files, SAMPLE.grant.id)  # waiting
    reject = Record.model_validate(
        {
            "id": "rec-reject-field",
            "workspace_id": SAMPLE.workspace.id,
            "grant_id": SAMPLE.grant.id,
            "author": "user",
            "author_user_id": SAMPLE.user.id,
            "written_at": "2023-01-12T16:00:00+00:00",
            "data": {
                "kind": "confirmation",
                "record_ids": ["rec-line-field"],
                "decision": "rejected",
            },
        }
    )
    assert not applies_to_is_matchable("Field Work", [line, reject], files, SAMPLE.grant.id)


def test_the_guidance_says_to_flag_a_narrower_clause_rather_than_widen_it():
    write_term = next(t for t in tool_definitions() if t["name"] == "write_term")
    flat = " ".join(write_term["description"].split())
    assert "names something narrower than any line, don't widen it: flag the term" in flat
