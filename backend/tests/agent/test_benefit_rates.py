"""The agent reads a fringe benefit rate agreement as rate terms (ruling 61).

One term per employee group and period: applies_to is the group, cited from the row's own name
for it, and effective_from / effective_to are the row's From and To dates. A provisional row
"Until Amended" has no end, and its citation shows it's provisional; there is no special state.

The recorded input is the seed's rate agreement PDF (data/samples/salt-marsh-carbon on branch
165-sample-content, PR 218), copied into tests/agent/fixtures. No model is called: the label
lines carry the page citations the API returns for a PDF, and code checks them with the quote
finder against the real file.
"""

import hashlib
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from anthropic.types import CitationPageLocation

from app.agent.citations import LabelLine
from app.agent.context import RunContext
from app.agent.desk import RATE_AGREEMENT_GUIDANCE, trigger_section
from app.agent.fields import TERM_FIELDS
from app.agent.prompts import SYSTEM_PROMPT
from app.agent.rulebook import load_rulebook
from app.agent.tools import run_tool
from app.contracts.fixtures import load_sample_grant
from app.contracts.records import BenefitGroup, Rate
from app.contracts.runs import Trigger, TriggerKind

from .fakes import sample_inputs

PDF = (Path(__file__).parent / "fixtures" / "rate_agreement_2025-05-28.pdf").read_bytes()
ARRIVED = datetime.fromisoformat("2025-06-16T18:00:00+00:00")
SAMPLE = load_sample_grant()
RATE_FILE = SAMPLE.files[0].model_copy(
    update={
        "id": "file-rate-agreement",
        "name": "rate_agreement_2025-05-28.pdf",
        "media_type": "application/pdf",
        "storage_path": "ws-sample/grant-sample/file-rate-agreement/rate_agreement_2025-05-28.pdf",
        "sha256": hashlib.sha256(PDF).hexdigest(),
        "arrived_at": ARRIVED,
    }
)

AGREEMENT_DATE = "AGREEMENT DATE: 05/28/2025"
PROVISIONAL = (
    "PROV. 07/01/2026 Until Amended Use same rates and conditions as those cited for fiscal "
    "year ending June 30, 2026"
)
# The rows as the PDF prints them: (rate, group as printed, the group).
FY25 = [
    ("34.80", "Academic", BenefitGroup.ACADEMIC),
    ("14.60", "Limited", BenefitGroup.LIMITED),
    ("4.50", "No Benefit Eligibility", BenefitGroup.NO_BENEFIT_ELIGIBILITY),
    ("43.00", "Staff", BenefitGroup.STAFF),
    ("2.90", "Student", BenefitGroup.STUDENT),
]
FY26 = [
    ("35.20", "Academic", BenefitGroup.ACADEMIC),
    ("15.00", "Limited", BenefitGroup.LIMITED),
    ("5.00", "No Benefit Eligibility", BenefitGroup.NO_BENEFIT_ELIGIBILITY),
    ("44.00", "Staff", BenefitGroup.STAFF),
    ("2.50", "Student", BenefitGroup.STUDENT),
]
YEARS = {"fy25": ("07/01/2024", "06/30/2025", FY25), "fy26": ("07/01/2025", "06/30/2026", FY26)}


def context() -> RunContext:
    base = sample_inputs(
        now=ARRIVED, trigger=Trigger(kind=TriggerKind.FILE, id=RATE_FILE.id), records=[]
    )
    read = base.read_file
    inputs = replace(
        base,
        files=[*base.files, RATE_FILE],
        read_file=lambda f: PDF if f.id == RATE_FILE.id else read(f),
    )
    ctx = RunContext(inputs=inputs, rulebook=load_rulebook())
    result, error = run_tool(ctx, "open_file", {"file_id": RATE_FILE.id})
    assert not error, result
    return ctx


def label(ctx: RunContext, name: str, value: str, passage: str) -> None:
    """A label line with the page citation the API gives for a passage of the PDF."""
    cite = CitationPageLocation(
        type="page_location",
        cited_text=passage,
        document_index=0,
        start_page_number=1,
        end_page_number=2,
    )
    ctx.labels[name] = LabelLine(name, value, [cite])


def row(start: str, end: str, rate: str, printed: str) -> str:
    return f"FIXED {start} {end} {rate} All {printed}"


def write_rate(ctx: RunContext, key: str, values: list[dict[str, str]]) -> tuple[str, bool]:
    label(ctx, f"{key}_dated", "05/28/2025", AGREEMENT_DATE)
    values = [{"field": "dated", "label": f"{key}_dated", "value": "2025-05-28"}, *values]
    return run_tool(ctx, "write_term", {"kind": "rate", "values": values})


def write_fixed(ctx: RunContext, year: str, rate: str, printed: str, group: BenefitGroup):
    start, end, _ = YEARS[year]
    passage = row(start, end, rate, printed)
    key = f"{year}_{group.value}"
    label(ctx, f"{key}_name", printed, passage)
    label(ctx, f"{key}_rate", rate, passage)
    label(ctx, f"{key}_group", printed, passage)
    label(ctx, f"{key}_from", start, passage)
    label(ctx, f"{key}_to", end, passage)
    return write_rate(
        ctx,
        key,
        [
            {"field": "name", "label": f"{key}_name"},
            {"field": "rate", "label": f"{key}_rate"},
            {"field": "applies_to", "label": f"{key}_group", "value": group.value},
            {"field": "effective_from", "label": f"{key}_from"},
            {"field": "effective_to", "label": f"{key}_to"},
        ],
    )


def write_provisional(ctx: RunContext, rate: str, printed: str, group: BenefitGroup):
    """The provisional row's term for a group: its start from the provisional row, and its rate,
    group and name from the fiscal year 2026 row it points back to."""
    points_to = row("07/01/2025", "06/30/2026", rate, printed)
    key = f"prov_{group.value}"
    label(ctx, f"{key}_name", printed, points_to)
    label(ctx, f"{key}_rate", rate, points_to)
    label(ctx, f"{key}_group", printed, points_to)
    label(ctx, f"{key}_from", "07/01/2026", PROVISIONAL)
    return write_rate(
        ctx,
        key,
        [
            {"field": "name", "label": f"{key}_name"},
            {"field": "rate", "label": f"{key}_rate"},
            {"field": "applies_to", "label": f"{key}_group", "value": group.value},
            {"field": "effective_from", "label": f"{key}_from"},
        ],
    )


def last_rate(ctx: RunContext) -> Rate:
    data = ctx.staged[-1].record.data
    assert isinstance(data, Rate)
    return data


def test_a_fixed_row_is_a_rate_term_with_its_group_and_dates():
    ctx = context()
    result, error = write_fixed(ctx, "fy26", "15.00", "Limited", BenefitGroup.LIMITED)
    assert not error, result
    rate = last_rate(ctx)
    assert rate.applies_to is not None and rate.applies_to.value == BenefitGroup.LIMITED
    assert rate.applies_to.text == "Limited"
    assert rate.rate.value == Decimal("0.15")  # 15.00 in the agreement's percent column
    assert rate.effective_from is not None and rate.effective_from.value == date(2025, 7, 1)
    assert rate.effective_to is not None and rate.effective_to.value == date(2026, 6, 30)
    for cited in (rate.rate, rate.applies_to, rate.effective_from, rate.effective_to):
        assert cited.citation is not None and cited.citation.match in ("exact", "close")
        passage, text = cited.citation.passage, cited.text
        assert passage is not None and text is not None and text in passage


def test_every_group_and_period_gets_its_own_term():
    ctx = context()
    for year in ("fy25", "fy26"):
        for rate, printed, group in YEARS[year][2]:
            result, error = write_fixed(ctx, year, rate, printed, group)
            assert not error, (year, printed, result)
    for rate, printed, group in FY26:
        result, error = write_provisional(ctx, rate, printed, group)
        assert not error, ("provisional", printed, result)
    rates = [s.record.data for s in ctx.staged if isinstance(s.record.data, Rate)]
    assert len(rates) == 15
    terms = {
        (
            r.applies_to.value if r.applies_to else None,
            r.effective_from.value if r.effective_from else None,
        ): r
        for r in rates
    }
    assert len(terms) == 15  # one per group and period
    for s in ctx.staged:  # every value was found in the PDF, none left unconfirmed
        assert not ctx.state().unconfirmed_values(s.record), s.record.id
    assert terms[(BenefitGroup.NO_BENEFIT_ELIGIBILITY, date(2024, 7, 1))].rate.value == Decimal(
        "0.045"
    )
    assert terms[(BenefitGroup.ACADEMIC, date(2025, 7, 1))].rate.value == Decimal("0.352")


def test_a_provisional_row_runs_until_amended_and_its_citation_shows_it():
    ctx = context()
    result, error = write_provisional(ctx, "44.00", "Staff", BenefitGroup.STAFF)
    assert not error, result
    rate = last_rate(ctx)
    assert rate.effective_to is None  # until amended
    assert rate.effective_from is not None and rate.effective_from.value == date(2026, 7, 1)
    start = rate.effective_from.citation
    assert start is not None and start.passage is not None
    assert "PROV." in start.passage and "Until Amended" in start.passage
    assert rate.rate.value == Decimal("0.44")
    assert rate.applies_to is not None and rate.applies_to.value == BenefitGroup.STAFF


def test_until_amended_as_an_end_date_is_refused_with_what_to_do():
    ctx = context()
    label(ctx, "p_name", "Staff", row("07/01/2025", "06/30/2026", "44.00", "Staff"))
    label(ctx, "p_rate", "44.00", row("07/01/2025", "06/30/2026", "44.00", "Staff"))
    label(ctx, "p_group", "Staff", row("07/01/2025", "06/30/2026", "44.00", "Staff"))
    label(ctx, "p_from", "07/01/2026", PROVISIONAL)
    label(ctx, "p_to", "Until Amended", PROVISIONAL)
    result, error = write_rate(
        ctx,
        "p",
        [
            {"field": "name", "label": "p_name"},
            {"field": "rate", "label": "p_rate"},
            {"field": "applies_to", "label": "p_group", "value": "staff"},
            {"field": "effective_from", "label": "p_from"},
            {"field": "effective_to", "label": "p_to"},
        ],
    )
    assert error and "leaves effective_to out" in result
    assert not ctx.staged


@pytest.mark.parametrize("given", ["faculty", None, "Staff"])
def test_a_group_has_to_be_one_of_the_five(given: str | None):
    ctx = context()
    passage = row("07/01/2025", "06/30/2026", "44.00", "Staff")
    label(ctx, "g_name", "Staff", passage)
    label(ctx, "g_rate", "44.00", passage)
    label(ctx, "g_group", "Staff", passage)
    group: dict[str, str] = {"field": "applies_to", "label": "g_group"}
    if given is not None:
        group["value"] = given
    result, error = write_rate(
        ctx,
        "g",
        [{"field": "name", "label": "g_name"}, {"field": "rate", "label": "g_rate"}, group],
    )
    assert error and "academic, limited, no_benefit_eligibility, staff, student" in result
    assert not ctx.staged


def test_a_rate_with_no_group_reads_its_number_as_before():
    """Only a benefit rate reads a bare number as a percent; a percent sign still reads as one."""
    ctx = context()
    passage = row("07/01/2025", "06/30/2026", "44.00", "Staff")
    label(ctx, "n_name", "Staff", passage)
    label(ctx, "n_rate", "44.00", passage)
    result, error = write_rate(
        ctx, "n", [{"field": "name", "label": "n_name"}, {"field": "rate", "label": "n_rate"}]
    )
    assert not error, result
    rate = last_rate(ctx)
    assert rate.rate.value == Decimal("44.00") and rate.applies_to is None


def test_a_file_run_tells_the_agent_how_to_read_a_rate_agreement():
    ctx = context()
    first = trigger_section(ctx)[0]["text"]
    assert RATE_AGREEMENT_GUIDANCE in first
    flat = " ".join(RATE_AGREEMENT_GUIDANCE.split())
    assert "each employee group in each period" in flat
    assert '"Until Amended", has no effective_to' in flat
    assert "don't mark it yourself" in flat
    assert "applies_to (cited employee group" in TERM_FIELDS


def test_the_agent_flags_what_the_recalculation_cant_see():
    flat = " ".join(SYSTEM_PROMPT.split())
    assert "Code recalculates a benefit charge" in flat
    assert "such as a stipend or a participant support payment" in flat
    assert "a rate from the wrong year" in flat and "the rate for the year it was earned" in flat
