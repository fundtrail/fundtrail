"""The evidence report (decision 0022) on the sample grant."""

import hashlib
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.contracts.charges import Charge
from app.contracts.checks import (
    Bucket,
    ChargeStatus,
    ChecklistEntry,
    ChecksOutput,
    GrantNote,
    GrantStatus,
    ItemSource,
    Problem,
    Reason,
)
from app.contracts.evidence import EvidenceFile, Source
from app.contracts.mail import HeldMail, HoldReason
from app.contracts.records import (
    Answer,
    Author,
    Bill,
    Citation,
    CitedMoney,
    ImageBox,
    Judgment,
    Match,
    Record,
)
from app.contracts.runs import Trigger, TriggerKind
from app.contracts.threads import ThreadMessage
from app.packet import (
    ReportInputs,
    Signing,
    build_report,
)
from app.packet.content import SECTION_TITLES, report_view
from app.packet.view import Heading, Para, Quote, Section, Table

from .sample import APRIL_9, APRIL_10, SAMPLE, USER, flat, pdf_pages, sample_inputs, user_record

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


def held(id: str, sender: str, subject: str) -> HeldMail:
    return HeldMail(
        id=id,
        workspace_id="ws-sample",
        grant_id="grant-sample",
        sender=sender,
        reason=HoldReason.UNKNOWN_SENDER,
        source_ref=f"gmail-{id}",
        subject=subject,
        held_at=datetime(2026, 3, 2, 9, tzinfo=UTC),
        files=(),
    )


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
    sign_off = Signing(
        author_user_id=USER.id,
        signed_at=APRIL_9,
        note="Signed off with one term waiting – the “extension” is on file.",
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
    return sample_inputs(
        APRIL_9,
        records=(*base.records, accepted),
        checks=checks,
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
    assert "As of Apr 10, 2026, 17:00 Coordinated Universal Time (UTC)" in first


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
    assert "End date in force: Jan 31, 2027." in text
    assert "In force" not in text  # only the end date is called in force
    assert "Term Says Confirmed" in text
    assert (
        "Period of performance Feb 1, 2023 to Jan 31, 2026 "
        "Confirmed by Sample Accountant, Jan 12, 2023" in text
    )
    assert (
        "Period of performance ends Jan 31, 2027 Confirmed by Sample Accountant, Apr 10, 2026"
        in text
    )
    assert "Funder National Science Foundation (NSF)" in text
    assert "As of" not in text  # the title already says it
    assert "Funding notice Amendment 000, New Project, adds $120,000.00" in text
    assert "Spending against the award's limit: $3,420.00 of $120,000.00." in text
    assert "Over budget Confirmed Participant Support Costs $20,000.00 $0.00 No" in text
    assert "Dr. Jesse Sample, Program Officer, jesse.sample@funder.example" in text
    assert "Participant Support Costs: approved by Program Officer, through Research.gov" in text
    assert "Materials and Supplies $40,000.00 $1,240.00 No" in text
    assert "Charges by status Status Number Evidence complete 2 Possible conflict 0" in text
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
    mail = held("held-1", "unknown.vendor@vendor.example", "Invoice")
    text = texts(section(sample_inputs(held_mail=(mail,)), 2))
    assert "Held mail" in text
    assert "unknown.vendor@vendor.example Mar 2, 2026 Unknown sender Invoice" in text


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
            charges=(
                base.checks.charges[0],
                base.checks.charges[1].model_copy(
                    update={"net_cents": 0, "reversed": True, "corrections": ("chg-l-1003",)}
                ),
                status,
            ),
            records=(),
            grants=(),
            questions=(),
            notes=(),
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
    assert "Apr 10, 2026 Evidence complete New end date confirmed. Feb 20, 2026 is inside" in text


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
    with pytest.raises(ValueError, match="one status per charge"):
        sample_inputs(checks=base.checks.model_copy(update={"charges": base.checks.charges[:1]}))
    other_grant = held("held-x", "a@vendor.example", "x").model_copy(
        update={"grant_id": "grant-other"}
    )
    with pytest.raises(ValueError, match="belongs to the grant"):
        sample_inputs(held_mail=(other_grant,))


def test_a_waiting_term_cites_its_file_and_a_rejected_one_doesnt():
    waiting = sample_inputs(APRIL_9)
    cited, uncited = texts(section(waiting, 6)).split("Files on the grant that no record cites")
    assert "extension_notice.txt" in cited
    assert "extension_notice.txt" not in uncited
    rejection = user_record(
        "rec-reject-extension",
        APRIL_9,
        {"kind": "confirmation", "record_ids": ["rec-period-extension"], "decision": "rejected"},
    )
    rejected = sample_inputs(APRIL_9, records=(*waiting.records, rejection))
    cited, uncited = texts(section(rejected, 6)).split("Files on the grant that no record cites")
    assert "extension_notice.txt" not in cited
    assert "extension_notice.txt Google Drive, arrived Apr 9, 2026" in uncited


def test_the_history_wording_is_w2s():
    from app.checks.history import describe_trigger

    inputs = sample_inputs()
    entry = inputs.history[-1]
    about = next(r for r in inputs.records if r.id == entry.trigger.id)
    trigger = describe_trigger(entry, about, inputs.records)
    assert trigger == "new end date confirmed"
    assert "New end date confirmed. Feb 20, 2026 is inside the period in force." in texts(
        section(inputs, 5)
    )


def test_a_charge_with_nothing_netted_shows_its_own_amount():
    table = section(sample_inputs(), 4).blocks[0]
    assert isinstance(table, Table)
    assert table.rows[0][2] == "$1,240.00"  # net_cents is None: no net line


# Review fixes


def agent_record(id: str, written_at: datetime, data: dict[str, Any]) -> Record:
    return Record.model_validate(
        {
            "id": id,
            "workspace_id": "ws-sample",
            "grant_id": "grant-sample",
            "author": "agent",
            "written_at": written_at,
            "data": data,
        }
    )


def test_long_notes_reasoning_and_subjects_never_stop_the_report():
    note = "The extension notice moves the end date. " * 100  # about 4,000 characters
    base = signed_inputs()
    long_note = tuple(
        r.model_copy(update={"data": r.data.model_copy(update={"note": note})})
        if r.id == "rec-accept-l-1002"
        else r
        for r in base.records
    )
    dispute = agent_record(
        "rec-dispute",
        APRIL_9,
        {
            "kind": "dispute",
            "charge_id": "chg-l-1002",
            "check": "period_of_performance",
            "reasoning": "The order was placed before the end date. " * 100,
            "quotes": [
                {
                    "file_id": "file-sequencing-statement",
                    "passage": "From",
                    "location": {
                        "type": "char_location",
                        "start_char_index": 0,
                        "end_char_index": 4,
                    },
                    "match": "exact",
                }
            ],
        },
    )
    confirm = user_record(
        "rec-confirm-dispute", APRIL_9, {"kind": "confirmation", "record_ids": ["rec-dispute"]}
    )
    mail = tuple(
        held(
            f"held-{i}",
            f"sender{i}@vendor.example",
            "Quarterly statement and remittance details " * 60,
        )
        for i in range(3)
    )
    inputs = sample_inputs(
        APRIL_9,
        records=(*long_note, dispute, confirm),
        checks=base.checks,
        sign_off=base.sign_off,
        held_mail=mail,
    )
    pages = pdf_pages(build_report(inputs))
    # Read the pages as one flow, without each page's header and footer and the
    # table headers repeated at the top of a page.
    furniture = re.compile(
        r"Evidence report · SYN-2300117 Signed · as of [^U]* UTC|Page \d+ of \d+"
        r"|When Who Decision About Detail|Sender Arrived Subject"
    )
    text = flat(" ".join(furniture.sub(" ", flat(p)) for p in pages))
    assert text.count("The extension notice moves the end date.") >= 100
    assert text.count("The order was placed before the end date.") >= 100
    assert text.count("Quarterly statement and remittance details") >= 180
    for i, page in enumerate(pages, start=1):
        assert f"Page {i} of {len(pages)}" in flat(page)


# Curly quotes, dashes, degrees, micro, times, plus-minus, section, accented
# names, euro and pound, an arrow, and a Romanian s with a comma below.
CHARACTERS = "‘a’ “b” 1–2 — 4°C 200 μL 3×2 ±0.5 § 2 José Peña Müller Erdős Brașov €12 £9 A→B"


def test_every_character_of_a_quote_comes_back_from_the_pdf():
    base = sample_inputs()
    passage = CHARACTERS + " non‑breaking zero​width"

    def with_passage(r: Record) -> Record:
        assert isinstance(r.data, Judgment)
        quote = r.data.quotes[0].model_copy(update={"passage": passage})
        return r.model_copy(update={"data": r.data.model_copy(update={"quotes": (quote,)})})

    records = tuple(with_passage(r) if r.id == "rec-allowable-l-1001" else r for r in base.records)
    text = flat(" ".join(pdf_pages(build_report(sample_inputs(records=records)))))
    assert "“" + CHARACTERS in text
    assert "non‑breaking" in text


def test_a_photo_part_prints_the_value_read_at_that_place():
    base = sample_inputs()
    box = ImageBox(left=0.1, top=0.2, width=0.3, height=0.1)
    at_box = Citation(file_id="file-invoice-1001", passage=None, location=box, match=Match.EXACT)
    bill = next(r for r in base.records if r.id == "rec-bill-inv-1001")
    assert isinstance(bill.data, Bill)
    total = bill.data.total.model_copy(update={"citation": at_box})
    photo_bill = bill.model_copy(update={"data": bill.data.model_copy(update={"total": total})})

    def with_part(part: Citation) -> str:
        def swap(r: Record) -> Record:
            if r.id == bill.id:
                return photo_bill
            if r.id == "rec-link-l-1001":
                return r.model_copy(update={"data": r.data.model_copy(update={"part": part})})
            return r

        records = tuple(swap(r) for r in base.records)
        return texts(section(sample_inputs(records=records), 5))

    assert "Cited: invoice_1001.txt, page 1, value as read: $1,240.00" in with_part(at_box)
    elsewhere = at_box.model_copy(update={"location": box.model_copy(update={"top": 0.5})})
    text = with_part(elsewhere)
    assert "Cited: invoice_1001.txt, page 1" in text
    assert "value as read" not in text


def test_an_answer_on_a_flag_isnt_paired_with_another_flag():
    base = sample_inputs()
    flag: dict[str, Any] = {
        "kind": "judgment",
        "charge_id": "chg-l-1001",
        "question": "flag",
        "text": "Is the core liner order a duplicate?",
        "answer": "unsure",
        "reasoning": "Two orders look alike.",
    }
    agent_flag = agent_record("rec-flag-agent", APRIL_10, flag)
    user_flag = user_record(
        "rec-flag-user", APRIL_10, {**flag, "text": "Is the shipping split right?"}
    )
    text = texts(section(sample_inputs(records=(*base.records, agent_flag, user_flag)), 3))
    assert "Is the shipping split right?" in text
    assert "Earlier answer" not in text


def test_only_the_preparer_signs_off():
    base = signed_inputs()
    assert base.sign_off is not None
    other = base.sign_off.model_copy(update={"author_user_id": "user-other"})
    with pytest.raises(ValueError, match="preparer's"):
        sample_inputs(APRIL_9, records=base.records, checks=base.checks, sign_off=other)


def test_a_waiting_term_isnt_in_force():
    text = texts(section(sample_inputs(APRIL_9), 1))
    assert "End date in force: Jan 31, 2026." in text
    assert "ends Jan 31, 2027" not in text


def test_over_budget_and_over_the_limit_come_from_the_checks():
    base = sample_inputs()
    note = GrantNote(
        grant_id="grant-sample",
        check="budget",
        text="Materials and Supplies: $41,000.00 of $40,000.00",
        record_ids=("rec-budget-materials-and-supplies",),
    )
    over = GrantStatus(
        grant_id="grant-sample",
        problems=(Problem(check="budget", problem="over_limit", text="Over the limit."),),
        flagged=True,
    )
    checks = base.checks.model_copy(update={"notes": (note,), "grants": (over,)})
    text = texts(section(sample_inputs(checks=checks), 1))
    assert "Materials and Supplies $40,000.00 $1,240.00 Yes" in text
    assert "Other $60,000.00 $2,180.00 No" in text
    assert "of $120,000.00. Spending is over the award's limit." in text
    assert "Budget note: Materials and Supplies: $41,000.00 of $40,000.00" in text
    elsewhere = over.model_copy(update={"grant_id": "grant-other"})
    other = base.checks.model_copy(update={"grants": (elsewhere,)})
    assert "over the award's limit" not in texts(section(sample_inputs(checks=other), 1))


def test_a_thread_trigger_reads_as_the_screen_does():
    base = sample_inputs()
    message = ThreadMessage(
        id="msg-1",
        workspace_id="ws-sample",
        grant_id="grant-sample",
        charge_id="chg-l-1002",
        author=Author.USER,
        author_user_id=USER.id,
        text="Is run 7 inside the extension?",
        written_at=APRIL_10,
    )
    entry = base.history[-1].model_copy(
        update={"trigger": Trigger(kind=TriggerKind.THREAD_MESSAGE, id="msg-1")}
    )
    inputs = sample_inputs(history=(*base.history[:-1], entry), thread_messages=(message,))
    assert "The accountant wrote in the thread." in texts(section(inputs, 5))


def test_a_signed_report_is_built_at_the_sign_offs_time_from_this_grant_only():
    base = signed_inputs()
    with pytest.raises(ValueError, match="sign-off's own time"):
        sample_inputs(
            APRIL_10,
            records=base.records,
            checks=base.checks,
            sign_off=base.sign_off,
        )
    stray = base.records[0].model_copy(update={"grant_id": "grant-other"})
    with pytest.raises(ValueError, match="belongs to the grant"):
        sample_inputs(records=(*sample_inputs().records, stray))


def test_snoozed_grant_problems_show_until_and_note():
    snooze = user_record(
        "rec-snooze-grant",
        APRIL_10,
        {
            "kind": "snooze",
            "until": "2026-06-01",
            "note": "Waiting for the next notice.",
            "reasons": [{"check": "budget", "problem": "over_limit"}],
        },
    )
    base = sample_inputs()
    grant = GrantStatus(
        grant_id="grant-sample",
        problems=(
            Problem(check="budget", problem="over_limit", text="Spending is over the limit."),
        ),
        flagged=False,
        snoozed=True,
    )
    checks = base.checks.model_copy(update={"grants": (grant,)})
    text = texts(section(sample_inputs(records=(*base.records, snooze), checks=checks), 2))
    assert "Snoozed until Jun 1, 2026. Note: Waiting for the next notice." in text


def test_a_grant_with_no_charges_says_so():
    inputs = sample_inputs(
        charges=(),
        checks=ChecksOutput(charges=(), records=(), grants=(), questions=(), notes=()),
        history=(),
        terms=(),
        budget=None,
    )
    view = report_view(inputs)
    assert texts(view.sections[0]).count("No charges.") == 1
    assert texts(view.sections[1]).startswith("Nothing is open: there are no charges,")
    assert texts(view.sections[3]) == "No charges."
    assert texts(view.sections[4]) == "No charges."
    pages = pdf_pages(build_report(inputs))
    assert "Page 1 of" in flat(pages[0])


def test_the_font_checksums_are_on_file():
    fonts = BACKEND / "app" / "packet" / "fonts"
    for line in (fonts / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        assert hashlib.sha256((fonts / name).read_bytes()).hexdigest() == digest


def test_thread_messages_belong_to_the_grant():
    message = ThreadMessage(
        id="msg-x",
        workspace_id="ws-sample",
        grant_id="grant-other",
        charge_id="chg-l-1002",
        author=Author.USER,
        author_user_id=USER.id,
        text="Elsewhere",
        written_at=APRIL_10,
    )
    with pytest.raises(ValueError, match="belongs to the grant"):
        sample_inputs(thread_messages=(message,))


def test_an_approval_rules_item_names_the_rule():
    """Issue 115: an item an approval rule added prints the rule, not "by default"."""
    base = sample_inputs()
    l1001 = next(s for s in base.checks.charges if s.charge_id == "chg-l-1001")
    rule_item = ChecklistEntry(
        default_item="approval:rec-approval-rule",
        added_by=ItemSource.RULE,
        rule_id="rec-approval-rule",
        needed="The Program Officer's approval through Research.gov",
        filled=False,
    )
    with_rule = l1001.model_copy(update={"checklist": (*l1001.checklist, rule_item)})
    checks = base.checks.model_copy(
        update={"charges": tuple(with_rule if s is l1001 else s for s in base.checks.charges)}
    )
    text = texts(section(sample_inputs(checks=checks), 5))
    assert (
        "The Program Officer's approval through Research.gov: Missing (added by the approval rule "
        "Participant Support Costs: approved by Program Officer, through Research.gov)" in text
    )
