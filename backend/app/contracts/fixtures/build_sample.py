"""Writes the sample grant's JSON from its documents, so every citation's characters are counted, not typed.

    cd backend && uv run python -m app.contracts.fixtures.build_sample

The documents and ledger.csv are written by hand. This builds sample_grant.json
and answer_key.json from them, following docs/contracts.md section 15. A test
checks that the committed JSON is what this writes.
"""

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any

from ..evidence import storage_path
from . import ANSWER_KEY_FILE, DOCUMENTS_DIR, SAMPLE_GRANT_FILE, SampleGrant

WORKSPACE = "ws-sample"
GRANT = "grant-sample"
ACCOUNTANT = "00000000-0000-4000-8000-000000000001"

FILES: dict[str, tuple[str, str, str, str, dict[str, str]]] = {
    # file ID: (name, source, media type, arrived at, extra fields)
    "file-award-letter": ("award_letter.txt", "upload", "text/plain", "2023-01-12T15:00:00Z", {}),
    "file-invoice-1001": ("invoice_1001.txt", "upload", "text/plain", "2025-11-12T18:00:00Z", {}),
    "file-sequencing-statement": (
        "sequencing_statement.eml",
        "gmail",
        "message/rfc822",
        "2026-02-21T17:30:00Z",
        {
            "document_date": "2026-02-21",
            "sender": "robin.example@university.example",
            "source_ref": "gmail-synthetic-0001",
        },
    ),
    "file-extension-notice": (
        "extension_notice.txt",
        "drive",
        "text/plain",
        "2026-04-09T16:00:00Z",
        {"source_ref": "drive-synthetic-0001"},
    ),
}

ALLOWABLE = "Is this cost necessary and reasonable, and is it for this project?"


def text_of(file_id: str) -> str:
    return (DOCUMENTS_DIR / FILES[file_id][0]).read_text(encoding="utf-8")


def cite(file_id: str, passage: str) -> dict[str, Any]:
    """A char_location citation of a passage that appears exactly once in the file."""
    text = text_of(file_id)
    start = text.find(passage)
    assert start >= 0 and text.find(passage, start + 1) < 0, f"{passage!r} must appear once in {file_id}"
    return {
        "file_id": file_id,
        "passage": passage,
        "location": {"type": "char_location", "start_char_index": start, "end_char_index": start + len(passage)},
        "match": "exact",
    }


def value(file_id: str, passage: str, text: str, parsed: Any) -> dict[str, Any]:
    assert text in passage
    return {"value": parsed, "text": text, "citation": cite(file_id, passage)}


def money(file_id: str, passage: str, text: str) -> dict[str, Any]:
    cents = round(float(text.lstrip("$").replace(",", "")) * 100)
    return value(file_id, passage, text, cents)


def day(file_id: str, passage: str, text: str) -> dict[str, Any]:
    return value(file_id, passage, text, datetime.strptime(text, "%B %d, %Y").date().isoformat())


def words(file_id: str, passage: str, text: str | None = None) -> dict[str, Any]:
    return value(file_id, passage, text or passage, text or passage)


def record(
    id: str, at: str, data: dict[str, Any], *, by_agent: bool = True, replaces_id: str | None = None
) -> dict[str, Any]:
    r: dict[str, Any] = {
        "id": id,
        "workspace_id": WORKSPACE,
        "grant_id": GRANT,
        "author": "agent" if by_agent else "user",
        "written_at": at,
        "data": data,
    }
    if not by_agent:
        r["author_user_id"] = ACCOUNTANT
    if replaces_id:
        r["replaces_id"] = replaces_id
    return r


def records() -> list[dict[str, Any]]:
    award = "file-award-letter"
    award_dated = day(award, "Amendment Date: January 10, 2023", "January 10, 2023")

    def term(data: dict[str, Any]) -> dict[str, Any]:
        return {"dated": award_dated, **data}

    def budget_line(passage: str, name: str, amount: str, category: str) -> dict[str, Any]:
        return term(
            {
                "kind": "budget_line",
                "name": words(award, passage, name),
                "amount": money(award, passage, amount),
                "category": category,
            }
        )

    def person(passage: str, name: str, email: str, role: str) -> dict[str, Any]:
        return term(
            {
                "kind": "person",
                "name": words(award, passage, name),
                "email": words(award, passage, email),
                "role": words(award, passage, role),
            }
        )

    rule = (
        "Special conditions: Funds budgeted for Participant Support Costs may not be diverted by the awardee to "
        "other categories of expense without the prior written approval of the cognizant NSF Program Officer, "
        "requested through Research.gov."
    )
    at = "2023-01-12T15:00:00Z"
    terms = [
        record(
            "rec-period",
            at,
            term(
                {
                    "kind": "period_of_performance",
                    "start": day(award, "Period of Performance Start Date: February 1, 2023", "February 1, 2023"),
                    "end": day(award, "Period of Performance End Date: January 31, 2026", "January 31, 2026"),
                }
            ),
        ),
        record(
            "rec-budget-participant-support",
            at,
            budget_line(
                "F. Participant Support Costs                              $20,000",
                "Participant Support Costs",
                "$20,000",
                "participant_support",
            ),
        ),
        record(
            "rec-budget-other-direct-costs",
            at,
            budget_line(
                "G. Other Direct Costs                                    $100,000",
                "Other Direct Costs",
                "$100,000",
                "other_direct_costs",
            ),
        ),
        record(
            "rec-budget-materials-and-supplies",
            at,
            budget_line(
                "1. Materials and Supplies                              $40,000",
                "Materials and Supplies",
                "$40,000",
                "materials_and_supplies",
            ),
        ),
        record(
            "rec-budget-other",
            at,
            budget_line("6. Other                                               $60,000", "Other", "$60,000", "other"),
        ),
        record(
            "rec-person-pi",
            at,
            person(
                "Principal Investigator: Dr. Robin Example, robin.example@university.example, Example State University",
                "Dr. Robin Example",
                "robin.example@university.example",
                "Principal Investigator",
            ),
        ),
        record(
            "rec-person-program-officer",
            at,
            person(
                "Program Officer: Dr. Jesse Sample, jesse.sample@funder.example",
                "Dr. Jesse Sample",
                "jesse.sample@funder.example",
                "Program Officer",
            ),
        ),
        record(
            "rec-person-grants-officer",
            at,
            person(
                "Grants Officer: Casey Placeholder, casey.placeholder@funder.example",
                "Casey Placeholder",
                "casey.placeholder@funder.example",
                "Grants Officer",
            ),
        ),
        record(
            "rec-approval-rule",
            at,
            term(
                {
                    "kind": "approval_rule",
                    "applies_to": words(award, rule, "Participant Support Costs"),
                    "approver": words(award, rule, "Program Officer"),
                    "channel": words(award, rule, "Research.gov"),
                }
            ),
        ),
        record(
            "rec-notice-000",
            at,
            term(
                {
                    "kind": "notice",
                    "amendment_number": words(award, "Amendment Number: 000", "000"),
                    "amendment_type": words(award, "Amendment Type: New Project", "New Project"),
                    "obligated_by_amendment": money(award, "Amount Obligated by this Amendment: $120,000", "$120,000"),
                    "obligated_to_date": money(award, "Total Amount Obligated to Date: $120,000", "$120,000"),
                }
            ),
        ),
    ]
    confirm_terms = record(
        "rec-confirm-award-terms",
        "2023-01-12T16:00:00Z",
        {"kind": "confirmation", "record_ids": [t["id"] for t in terms]},
        by_agent=False,
    )

    invoice = "file-invoice-1001"
    invoice_line = "Sediment core liners, 50 count: $1,240.00"
    invoice_total = money(invoice, "Total Due: $1,240.00", "$1,240.00")
    bill_1001 = record(
        "rec-bill-inv-1001",
        "2025-11-12T18:00:00Z",
        {
            "kind": "bill",
            "total": invoice_total,
            "vendor": words(invoice, "Example Lab Supply Co."),
            "dated": day(invoice, "Invoice Date: November 12, 2025", "November 12, 2025"),
            "description": words(invoice, invoice_line, "Sediment core liners, 50 count"),
            "document_number": words(invoice, "Invoice Number: INV-1001", "INV-1001"),
            "items": [
                {
                    "description": words(invoice, invoice_line, "Sediment core liners, 50 count"),
                    "amount": money(invoice, invoice_line, "$1,240.00"),
                }
            ],
        },
    )

    statement = "file-sequencing-statement"
    service = "Service: Sediment DNA sequencing, run 7, 48 samples"
    statement_total = money(statement, "Total: $2,180.00", "$2,180.00")
    bill_seq = record(
        "rec-bill-seq-0207",
        "2026-02-21T17:30:00Z",
        {
            "kind": "bill",
            "total": statement_total,
            "vendor": words(statement, "Example Sequencing Core, a campus core facility", "Example Sequencing Core"),
            "dated": day(statement, "Statement Date: February 20, 2026", "February 20, 2026"),
            "description": words(statement, service, "Sediment DNA sequencing, run 7, 48 samples"),
            "document_number": words(statement, "USAGE STATEMENT SEQ-0207", "SEQ-0207"),
        },
    )

    def charge_records(
        line: str, at: str, bill: dict[str, Any], total: dict[str, Any], item: str, budget: str, why: str
    ) -> list[dict[str, Any]]:
        charge = f"chg-{line.lower()}"
        amount = total["value"]
        return [
            record(
                f"rec-link-{line.lower()}",
                at,
                {
                    "kind": "link",
                    "record_id": bill["id"],
                    "charge_id": charge,
                    "amount_cents": amount,
                    "part": total["citation"],
                    "default_item": item,
                    "reason": why,
                },
            ),
            record(
                f"rec-budget-{line.lower()}",
                at,
                {
                    "kind": "budget_assignment",
                    "charge_id": charge,
                    "record_id": budget,
                    "reason": f"The bill is for {bill['data']['description']['value'].lower()}.",
                },
            ),
            record(
                f"rec-allowable-{line.lower()}",
                at,
                {
                    "kind": "judgment",
                    "charge_id": charge,
                    "question": "allowable",
                    "text": ALLOWABLE,
                    "answer": "supports",
                    "reasoning": (
                        "The bill is for field and lab work on the sediment survey this award funds, "
                        "at an ordinary price for the quantity."
                    ),
                    "quotes": [bill["data"]["description"]["citation"]],
                    "rests_on": [bill["id"]],
                },
            ),
        ]

    l1001 = charge_records(
        "L-1001",
        "2025-11-14T00:00:00Z",
        bill_1001,
        invoice_total,
        "bill",
        "rec-budget-materials-and-supplies",
        "The ledger line's reference INV-1001, vendor and amount match the invoice.",
    )
    l1002 = charge_records(
        "L-1002",
        "2026-02-24T00:00:00Z",
        bill_seq,
        statement_total,
        "usage_statement",
        "rec-budget-other",
        "The ledger line's reference SEQ-0207, vendor and amount match the usage statement.",
    )

    extension = "file-extension-notice"
    new_end = record(
        "rec-period-extension",
        "2026-04-09T16:00:00Z",
        {
            "kind": "period_of_performance",
            "dated": day(extension, "Amendment Date: January 15, 2026", "January 15, 2026"),
            "end": day(
                extension,
                "Amendment Description: This amendment extends the end date from January 31, 2026 to "
                "January 31, 2027. No additional funds are provided.",
                "January 31, 2027",
            ),
        },
    )
    confirm_extension = record(
        "rec-confirm-extension",
        "2026-04-10T16:00:00Z",
        {"kind": "confirmation", "record_ids": [new_end["id"]]},
        by_agent=False,
    )
    return [*terms, confirm_terms, bill_1001, *l1001, bill_seq, *l1002, new_end, confirm_extension]


def sample_grant() -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for file_id, (name, source, media_type, arrived_at, extra) in FILES.items():
        files.append(
            {
                "id": file_id,
                "workspace_id": WORKSPACE,
                "grant_id": GRANT,
                "source": source,
                "name": name,
                "media_type": media_type,
                "storage_path": storage_path(WORKSPACE, GRANT, file_id, name),
                "sha256": hashlib.sha256((DOCUMENTS_DIR / name).read_bytes()).hexdigest(),
                "arrived_at": arrived_at,
                **extra,
            }
        )

    def charge(line: str, cost: str, posted: str, cents: int, description: str, account: str, vendor: str, ref: str):
        return {
            "id": f"chg-{line.lower()}",
            "workspace_id": WORKSPACE,
            "grant_id": GRANT,
            "ledger_line_id": line,
            "transaction_date": cost,
            "posting_date": posted,
            "arrived_at": datetime.combine(date.fromisoformat(posted), datetime.min.time(), UTC).isoformat(),
            "amount_cents": cents,
            "description": description,
            "account": account,
            "vendor": vendor,
            "reference": ref,
        }

    return {
        "user": {"id": ACCOUNTANT, "email": "accountant@university.example", "name": "Sample Accountant"},
        "workspace": {
            "id": WORKSPACE,
            "name": "Sample grant",
            "owner_id": ACCOUNTANT,
            "clock_now": "2026-04-10T17:00:00Z",
        },
        "grant": {
            "id": GRANT,
            "workspace_id": WORKSPACE,
            "funder": "NSF",
            "award_number": "SYN-2300117",
            "title": "Sediment Microbiome Survey of Example Bay",
        },
        "charges": [
            charge(
                "L-1001",
                "2025-11-12",
                "2025-11-14",
                124000,
                "Sediment core liners",
                "55016 Lab Instruments and Supplies",
                "Example Lab Supply Co.",
                "INV-1001",
            ),
            charge(
                "L-1002",
                "2026-02-20",
                "2026-02-24",
                218000,
                "Sediment DNA sequencing run 7",
                "59009 Recharge-Other Expenses",
                "Example Sequencing Core",
                "SEQ-0207",
            ),
        ],
        "files": files,
        "records": records(),
        "default_items": {
            "L-1001": [{"key": "bill", "needed": "A bill that adds up to the charge", "amount_cents": 124000}],
            "L-1002": [{"key": "usage_statement", "needed": "The facility's usage statement", "amount_cents": 218000}],
        },
    }


def answer_key() -> dict[str, Any]:
    award, extension = "award_letter.txt", "extension_notice.txt"
    dated = {"dated": "2023-01-10"}

    def expect(kind: str, file: str, **fields: str) -> dict[str, Any]:
        return {"kind": kind, "file": file, "fields": fields}

    return {
        "case": "sample-grant-extension-notice",
        "award_number": "SYN-2300117",
        "records": [
            expect("period_of_performance", award, **dated, start="2023-02-01", end="2026-01-31"),
            expect("budget_line", award, **dated, name="Participant Support Costs", amount="2000000"),
            expect("budget_line", award, **dated, name="Other Direct Costs", amount="10000000"),
            expect("budget_line", award, **dated, name="Materials and Supplies", amount="4000000"),
            expect("budget_line", award, **dated, name="Other", amount="6000000"),
            expect(
                "person",
                award,
                **dated,
                name="Dr. Robin Example",
                email="robin.example@university.example",
                role="Principal Investigator",
            ),
            expect(
                "person",
                award,
                **dated,
                name="Dr. Jesse Sample",
                email="jesse.sample@funder.example",
                role="Program Officer",
            ),
            expect(
                "person",
                award,
                **dated,
                name="Casey Placeholder",
                email="casey.placeholder@funder.example",
                role="Grants Officer",
            ),
            expect(
                "approval_rule",
                award,
                **dated,
                applies_to="Participant Support Costs",
                approver="Program Officer",
                channel="Research.gov",
            ),
            expect(
                "notice",
                award,
                **dated,
                amendment_number="000",
                amendment_type="New Project",
                obligated_by_amendment="12000000",
                obligated_to_date="12000000",
            ),
            expect(
                "bill",
                "invoice_1001.txt",
                total="124000",
                vendor="Example Lab Supply Co.",
                dated="2025-11-12",
                document_number="INV-1001",
                **{"items[0].amount": "124000"},
            ),
            expect(
                "bill",
                "sequencing_statement.eml",
                total="218000",
                vendor="Example Sequencing Core",
                dated="2026-02-20",
                document_number="SEQ-0207",
            ),
            expect("period_of_performance", extension, dated="2026-01-15", end="2027-01-31"),
        ],
        "links": [
            {"file": "invoice_1001.txt", "line_id": "L-1001", "amount_cents": 124000},
            {"file": "sequencing_statement.eml", "line_id": "L-1002", "amount_cents": 218000},
        ],
        "budget_lines": [
            {"line_id": "L-1001", "budget_line": "Materials and Supplies"},
            {"line_id": "L-1002", "budget_line": "Other"},
        ],
        "answers": [
            {"line_id": "L-1001", "question": "allowable", "answer": "supports"},
            {"line_id": "L-1002", "question": "allowable", "answer": "supports"},
        ],
        "buckets": [
            {"line_id": "L-1001", "at": "2025-11-14T12:00:00Z", "bucket": "evidence_complete"},
            {"line_id": "L-1001", "at": "2026-02-24T12:00:00Z", "bucket": "evidence_complete"},
            {"line_id": "L-1002", "at": "2026-02-24T12:00:00Z", "bucket": "possible_conflict"},
            {"line_id": "L-1001", "at": "2026-04-10T17:00:00Z", "bucket": "evidence_complete"},
            {"line_id": "L-1002", "at": "2026-04-10T17:00:00Z", "bucket": "evidence_complete"},
        ],
    }


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    grant = sample_grant()
    SampleGrant.model_validate(grant)  # it has to fit the contracts before it's written
    SAMPLE_GRANT_FILE.write_text(dumps(grant), encoding="utf-8")
    ANSWER_KEY_FILE.write_text(dumps(answer_key()), encoding="utf-8")


if __name__ == "__main__":
    main()
