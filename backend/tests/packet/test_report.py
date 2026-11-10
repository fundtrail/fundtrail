"""The evidence report (decision 0022) on the sample grant."""

import hashlib
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.contracts.charges import Charge
from app.contracts.checks import Bucket, ChargeStatus, ChecksOutput, Reason
from app.contracts.evidence import EvidenceFile, Source
from app.contracts.records import Answer, Bill, CitedMoney, Record
from app.packet import ChargeLedgerState, HeldMessage, ReportInputs, build_report
from app.packet.content import SECTION_TITLES, report_view
from app.packet.view import Heading, Para, Quote, Section, Table

from .sample import APRIL_9, APRIL_10, SAMPLE, flat, pdf_pages, sample_inputs, user_record

BACKEND = Path(__file__).resolve().parents[2]
FORBIDDEN = ("submitted", "filed", "certified")


def section(inputs: ReportInputs, number: int) -> Section:
    return report_view(inputs).sections[number - 1]


def texts(s: Section) -> str:
    """Everything a section says, as one string."""
    out: list[str] = []
    for b in s.blocks:
        if isinstance(b, Table):
            out += [*b.headers, *(cell for row in b.rows for cell in row)]
        elif isinstance(b, Quote):
            out += [b.passage, b.source]
        elif isinstance(b, Para | Heading):
            out.append(b.text)
    return flat(" ".join(out))


def signed_inputs() -> ReportInputs:
    """April 9, with L-1002's date conflict accepted with a note, then signed off."""
    base = sample_inputs(APRIL_9)
    accepted = user_record(
        "rec-accept-l-1002",
        APRIL_9,
        {
            "kind": "accepted_reason",
            "charge_id": "chg-l-1002",
            "reason": {"check": "period_of_performance", "problem": "after_end_date"},
            "note": "The extension notice moves the end date; it’s waiting for confirmation.",
        },
    )
    sign_off = user_record(
        "rec-sign-off",
        APRIL_9,
        {
            "kind": "sign_off",
            "note": "Signed off with one term waiting – the “extension” is on file.",
        },
    )
    l1002 = base.checks.charges[1]
    reasons = tuple(
        r.model_copy(update={"accepted_by": accepted.id})
        if r.check == "period_of_performance"
        else r
        for r in l1002.reasons
    )
    checks = base.checks.model_copy(
        update={
            "charges": (
                base.checks.charges[0],
                l1002.model_copy(update={"reasons": reasons, "accepted": True, "flagged": False}),
            )
        }
    )
    ledger = (base.ledger[0], base.ledger[1].model_copy(update={"ready": True}))
    return sample_inputs(
        APRIL_9,
        records=(*base.records, accepted, sign_off),
        checks=checks,
        ledger=ledger,
        sign_off=sign_off,
    )


@pytest.fixture(scope="module")
def draft_pdf() -> bytes:
    return build_report(sample_inputs())


@pytest.fixture(scope="module")
def signed_pdf() -> bytes:
    return build_report(signed_inputs())


# The whole report


def test_the_seven_sections_come_in_order(draft_pdf: bytes):
    assert [s.title for s in report_view(sample_inputs()).sections] == list(SECTION_TITLES)
    text = flat(" ".join(pdf_pages(draft_pdf)))
    positions = [text.index(title) for title in SECTION_TITLES]
    assert positions == sorted(positions)


def test_the_title_names_the_award_and_the_moment(draft_pdf: bytes):
    first = flat(pdf_pages(draft_pdf)[0])
    assert first.startswith("Evidence report")
    assert "SYN-2300117" in first
    assert "Sediment Microbiome Survey of Example Bay" in first
    assert "As of Apr 10, 2026, 17:00 UTC" in first


def test_every_page_of_a_draft_is_marked_and_numbered(draft_pdf: bytes):
    pages = pdf_pages(draft_pdf)
    assert len(pages) >= 2
    for i, page in enumerate(pages, start=1):
        page = flat(page)
        assert "Evidence report · SYN-2300117" in page
        assert "DRAFT · as of Apr 10, 2026, 17:00 UTC" in page
        assert f"Page {i} of {len(pages)}" in page


def test_a_signed_report_says_signed_on_every_page(signed_pdf: bytes):
    pages = pdf_pages(signed_pdf)
    for i, page in enumerate(pages, start=1):
        page = flat(page)
        assert "Signed · as of Apr 9, 2026, 17:00 UTC" in page
        assert "DRAFT" not in page
        assert f"Page {i} of {len(pages)}" in page


@pytest.mark.parametrize("which", ["draft", "signed"])
def test_no_word_claims_more_than_fundtrail_does(which: str, draft_pdf: bytes, signed_pdf: bytes):
    text = " ".join(pdf_pages(draft_pdf if which == "draft" else signed_pdf)).lower()
    for word in FORBIDDEN:
        assert word not in text


def test_the_page_is_us_letter(draft_pdf: bytes):
    assert b"/MediaBox [ 0 0 612 792 ]" in draft_pdf


# Same inputs, same bytes


def test_the_same_inputs_give_the_same_bytes(draft_pdf: bytes):
    assert build_report(sample_inputs()) == draft_pdf


def test_the_creation_date_is_the_workspace_now(draft_pdf: bytes):
    assert b"/CreationDate (D:20260410170000+00'00')" in draft_pdf
    assert build_report(sample_inputs(APRIL_9)) != draft_pdf


def test_the_bytes_dont_depend_on_the_process(draft_pdf: bytes):
    script = (
        "import hashlib, sys\n"
        "from tests.packet.sample import sample_inputs\n"
        "from app.packet import build_report\n"
        "sys.stdout.write(hashlib.sha256(build_report(sample_inputs())).hexdigest())\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": "12345"}
    out = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout == hashlib.sha256(draft_pdf).hexdigest()


# 1. Summary


def test_the_summary_has_the_terms_spending_counts_and_ledger_total():
    text = texts(section(sample_inputs(), 1))
    assert "Feb 1, 2023 to Jan 31, 2027" in text
    assert (
        "Confirmed by Sample Accountant, Jan 12, 2023; Confirmed by Sample Accountant, Apr 10, 2026"
        in text
    )
    assert "$120,000.00 total obligated to date (Amendment 000, New Project" in text
    assert "Spending against the award's limit: $3,420.00 of $120,000.00." in text
    assert "Materials and Supplies $40,000.00 $1,240.00 Within" in text
    assert "Dr. Jesse Sample, Program Officer, jesse.sample@funder.example" in text
    assert "Participant Support Costs: approved by Program Officer, through Research.gov" in text
    assert "Evidence complete 2 Possible conflict 0" in text
    assert "Accepted 0 Reversed 0 All charges 2" in text
    assert "Ready for closeout: 2 of 2 charges" in text
    assert (
        "Ledger total held by FundTrail: $3,420.00 across 2 ledger lines, "
        "latest posting date Feb 24, 2026." in text
    )


def test_accepted_charges_are_counted_on_their_own():
    text = texts(section(signed_inputs(), 1))
    assert "Evidence complete 1 Possible conflict 0" in text
    assert "Accepted 1 Reversed 0" in text


# 2. Open at sign-off


def test_nothing_is_open_once_the_extension_is_confirmed():
    assert texts(section(sample_inputs(), 2)).startswith("Nothing is open")


def test_an_open_charge_lists_its_failing_reasons_and_the_waiting_term():
    text = texts(section(sample_inputs(APRIL_9), 2))
    assert "L-1002 · Sediment DNA sequencing run 7 · $2,180.00 · Possible conflict" in text
    assert "Feb 20, 2026 is after the end date in force, Jan 31, 2026." in text
    assert "L-1001" not in text  # ready, so not open
    assert "inside the period" not in text  # passes aren't open items
    assert (
        "Period of performance: ends Jan 31, 2027 term_waiting "
        "A term read from extension_notice.txt" in text
    )


def test_held_mail_is_listed_as_open():
    mail = HeldMessage(
        id="held-1",
        sender="unknown.vendor@vendor.example",
        arrived_at=datetime(2026, 3, 2, 9, tzinfo=UTC),
        subject="Invoice",
    )
    text = texts(section(sample_inputs(held_mail=(mail,)), 2))
    assert "Mail held from unknown senders" in text
    assert "unknown.vendor@vendor.example Mar 2, 2026 Invoice" in text


# 3. Decisions


def test_the_sample_grant_has_no_decisions_to_list():
    assert texts(section(sample_inputs(), 3)).startswith("The accountant made no decisions")


def test_an_accepted_reason_is_listed_with_its_note():
    text = texts(section(signed_inputs(), 3))
    assert "Apr 9, 2026 Sample Accountant Accepted reason L-1002" in text
    assert "period_of_performance (after_end_date). One-off note: The extension notice" in text
    assert "Confirmation" not in text  # term confirmations aren't decisions here


def test_an_answer_and_a_typed_value_show_what_they_replaced():
    base = sample_inputs()
    agent_answer = next(r for r in base.records if r.id == "rec-allowable-l-1002")
    answer = user_record(
        "rec-answer-l-1002",
        APRIL_10,
        agent_answer.data.model_copy(
            update={"answer": Answer.UNSURE, "reasoning": "Run 7 may belong to the next project."}
        ).model_dump(),
        replaces_id=agent_answer.id,
    )
    bill = next(r for r in base.records if r.id == "rec-bill-inv-1001")
    assert isinstance(bill.data, Bill)
    typed = user_record(
        "rec-bill-typed",
        APRIL_10,
        bill.data.model_copy(update={"total": CitedMoney(value=123900)}).model_dump(),
        replaces_id=bill.id,
    )
    text = texts(section(sample_inputs(records=(*base.records, answer, typed)), 3))
    assert "Accountant's answer L-1002" in text
    assert "Answer: Unsure. Run 7 may belong to the next project." in text
    assert "Earlier answer (Agent, Feb 24, 2026): Supports." in text
    assert "Value typed" in text
    assert "total: $1,239.00 (was $1,240.00)" in text


# 4. Every charge


def test_every_charge_has_one_row():
    table = section(sample_inputs(), 4).blocks[0]
    assert isinstance(table, Table)
    assert [row[0].split("\n")[0] for row in table.rows] == ["L-1001", "L-1002"]
    assert table.rows[0][4] == "Materials and Supplies"
    assert table.rows[1][4] == "Other"
    assert table.rows[1][3] == "Evidence complete"
    assert table.rows[1][5] == "Feb 20, 2026 is inside the period in force."


def test_a_correction_sits_under_the_charge_it_corrects_with_the_net():
    base = sample_inputs()
    reversal = Charge(
        id="chg-l-1003",
        workspace_id="ws-sample",
        grant_id="grant-sample",
        ledger_line_id="L-1003",
        transaction_date=datetime(2026, 3, 1).date(),
        posting_date=datetime(2026, 3, 2).date(),
        arrived_at=datetime(2026, 3, 2, tzinfo=UTC),
        amount_cents=-218000,
        description="Reversal of sequencing run 7",
        account="59009 Recharge-Other Expenses",
        original_line_id="L-1002",
    )
    status = ChargeStatus(
        grant_id="grant-sample",
        charge_id="chg-l-1003",
        bucket=Bucket.EVIDENCE_COMPLETE,
        reasons=(
            Reason(
                check="checklist",
                problem="passes",
                text="Every checklist item is filled.",
                bucket=Bucket.EVIDENCE_COMPLETE,
            ),
        ),
        checklist=(),
        flagged=False,
    )
    inputs = sample_inputs(
        charges=(*base.charges, reversal),
        checks=ChecksOutput(
            charges=(*base.checks.charges, status), records=(), grants=(), questions=(), notes=()
        ),
        ledger=(
            base.ledger[0],
            ChargeLedgerState(
                charge_id="chg-l-1002",
                net_cents=0,
                reversed=True,
                corrections=("chg-l-1003",),
                ready=True,
            ),
            ChargeLedgerState(charge_id="chg-l-1003", net_cents=-218000, ready=True),
        ),
    )
    table = section(inputs, 4).blocks[0]
    assert isinstance(table, Table)
    lines = [row[0].split("\n")[0] for row in table.rows]
    assert lines == ["L-1001", "L-1002", "L-1003 (correction)"]
    assert table.sub_rows == frozenset({2})
    assert table.rows[1][2] == "$2,180.00\nNet $0.00"
    assert table.rows[1][3] == "Evidence complete\nReversed"
    summary = texts(section(inputs, 1))
    assert "Evidence complete 2 Possible conflict 0" in summary
    assert "Reversed 1 All charges 3" in summary
    assert "$1,240.00 across 3 ledger lines" in summary


# 5. Each charge in full


def test_each_charge_shows_its_evidence_checks_answers_and_history():
    s = section(sample_inputs(), 5)
    text = texts(s)
    assert "L-1001 · Sediment core liners" in text
    assert "A bill that adds up to the charge: Filled (by default, amount $1,240.00)." in text
    assert (
        "Bill from Example Lab Supply Co. INV-1001, total $1,240.00, linked for $1,240.00" in text
    )
    quotes = [b for b in s.blocks if isinstance(b, Quote)]
    total = next(q for q in quotes if q.passage == "Total Due: $1,240.00")
    line = SAMPLE.document("file-invoice-1001")[:297].count("\n") + 1
    assert total.source == f"invoice_1001.txt, line {line}"
    assert "Code check Result Text period_of_performance Evidence complete" in text
    assert "Agent's answer, Nov 14, 2025: Is this cost necessary and reasonable" in text
    assert "Supports. The bill is for field and lab work" in text
    # Status history: dated changes of bucket with the reason for each.
    assert (
        "Feb 24, 2026 Possible conflict Ledger line L-1002 arrived. Feb 20, 2026 is after" in text
    )
    assert "Apr 10, 2026 Evidence complete Confirmation by the accountant." in text


def test_the_agents_rule_prints_with_its_title():
    base = sample_inputs()
    answer = next(r for r in base.records if r.id == "rec-allowable-l-1001")
    with_rule = answer.model_copy(update={"data": answer.data.model_copy(update={"rule": "R-7"})})
    records = tuple(with_rule if r.id == answer.id else r for r in base.records)
    inputs = sample_inputs(records=records, rule_titles={"R-7": "Necessary and reasonable"})
    assert "Rule R-7: Necessary and reasonable" in texts(section(inputs, 5))


# 6. Sources


def test_every_cited_file_is_listed_with_its_full_checksum(draft_pdf: bytes):
    table = section(sample_inputs(), 6).blocks[1]
    assert isinstance(table, Table)
    assert [row[0].split("\n")[0] for row in table.rows] == [
        "award_letter.txt",
        "invoice_1001.txt",
        "sequencing_statement.eml",
        "extension_notice.txt",
    ]
    assert "From robin.example@university.example" in table.rows[2][1]
    text = flat(" ".join(pdf_pages(draft_pdf)))
    for f in SAMPLE.files:
        assert f.sha256 in text


def test_files_nothing_cites_are_listed_apart():
    stray = EvidenceFile(
        id="file-stray",
        workspace_id="ws-sample",
        grant_id="grant-sample",
        source=Source.UPLOAD,
        name="lab_photo.jpg",
        media_type="image/jpeg",
        storage_path="ws-sample/grant-sample/file-stray/lab_photo.jpg",
        sha256="0" * 64,
        arrived_at=datetime(2026, 3, 3, tzinfo=UTC),
    )
    text = texts(section(sample_inputs(files=(*SAMPLE.files, stray)), 6))
    cited, uncited = text.split("Files on the grant that no record cites")
    assert "lab_photo.jpg" not in cited
    assert "lab_photo.jpg Upload, arrived Mar 3, 2026" in uncited


# 7. Sign-off


def test_a_draft_is_not_signed_and_leaves_reviewed_by_blank():
    text = texts(section(sample_inputs(), 7))
    assert text == "Not signed. This is a draft as of Apr 10, 2026, 17:00 UTC."
    blocks = section(sample_inputs(), 7).blocks
    assert blocks[-1].labels == ("Name", "Title", "Signature", "Date")  # type: ignore[union-attr]


def test_a_signed_report_prints_who_when_and_the_note_in_full(signed_pdf: bytes):
    s = section(signed_inputs(), 7)
    assert [b.text for b in s.blocks if isinstance(b, Para)] == [
        "Signed off by Sample Accountant (accountant@university.example) "
        "on Apr 9, 2026, 17:00 UTC.",
        "Note for the reviewer",
        "Signed off with one term waiting – the “extension” is on file.",
    ]
    text = flat(" ".join(pdf_pages(signed_pdf)))
    # Curly quotes and dashes survive into the PDF.
    assert "Signed off with one term waiting – the “extension” is on file." in text
    assert re.search(r"Reviewed by Name Title Signature Date", text)


def test_inputs_must_cover_every_charge():
    base = sample_inputs()
    with pytest.raises(ValueError, match="one entry per charge"):
        sample_inputs(ledger=base.ledger[:1])
    record: Record = base.records[0]
    with pytest.raises(ValueError, match="sign_off record"):
        sample_inputs(sign_off=record)
