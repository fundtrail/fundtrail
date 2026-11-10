"""Tests for the ledger file reader, against the sample grant (contracts.md section 15)."""

import io
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from openpyxl import Workbook

from app.contracts.charges import Charge
from app.contracts.fixtures import LEDGER_FILE, load_sample_grant
from app.ingest.ledger import (
    LedgerFileError,
    RejectedRow,
    read_ledger_file,
)

WORKSPACE = "ws-sample"
GRANT = "grant-sample"

HEADER = (
    "line_id,transaction_date,posting_date,amount,description,account,vendor,reference,"
    "original_line_id"
)
SAMPLE_CSV = "\n".join(
    [
        HEADER,
        "L-1001,2025-11-12,2025-11-14,1240.00,Sediment core liners,"
        "55016 Lab Instruments and Supplies,Example Lab Supply Co.,INV-1001,",
        "L-1002,2026-02-20,2026-02-24,2180.00,Sediment DNA sequencing run 7,"
        "59009 Recharge-Other Expenses,Example Sequencing Core,SEQ-0207,",
    ]
)


def _ids():
    counter = iter(range(1, 1000))
    return lambda: f"charge-{next(counter)}"


# The sample grant's clock when the award letter is uploaded, before either line posts.
BEFORE_ANY_POSTING = datetime(2023, 1, 12, tzinfo=UTC)


def _read(
    content: bytes | str,
    existing: tuple[str, ...] = (),
    now: datetime = BEFORE_ANY_POSTING,
):
    data = content.encode() if isinstance(content, str) else content
    return read_ledger_file(
        data,
        workspace_id=WORKSPACE,
        grant_id=GRANT,
        existing_line_ids=existing,
        now=now,
        new_id=_ids(),
    )


EXPECTED_SAMPLE = [
    Charge(
        id="charge-1",
        workspace_id=WORKSPACE,
        grant_id=GRANT,
        ledger_line_id="L-1001",
        transaction_date=date(2025, 11, 12),
        posting_date=date(2025, 11, 14),
        arrived_at=datetime(2025, 11, 14, tzinfo=UTC),
        amount_cents=124000,
        description="Sediment core liners",
        account="55016 Lab Instruments and Supplies",
        vendor="Example Lab Supply Co.",
        reference="INV-1001",
    ),
    Charge(
        id="charge-2",
        workspace_id=WORKSPACE,
        grant_id=GRANT,
        ledger_line_id="L-1002",
        transaction_date=date(2026, 2, 20),
        posting_date=date(2026, 2, 24),
        arrived_at=datetime(2026, 2, 24, tzinfo=UTC),
        amount_cents=218000,
        description="Sediment DNA sequencing run 7",
        account="59009 Recharge-Other Expenses",
        vendor="Example Sequencing Core",
        reference="SEQ-0207",
    ),
]


def _xlsx(rows: Sequence[Sequence[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_sample_grant_csv():
    result = _read(SAMPLE_CSV)
    assert result.charges == EXPECTED_SAMPLE
    assert result.skipped_line_ids == []
    assert result.rejected == []


def test_sample_grant_csv_with_byte_order_mark_and_windows_line_endings():
    result = _read(("﻿" + SAMPLE_CSV.replace("\n", "\r\n") + "\r\n").encode())
    assert result.charges == EXPECTED_SAMPLE
    assert result.rejected == []


def test_sample_grant_excel_with_typed_cells():
    header = HEADER.split(",")
    content = _xlsx(
        [
            header,
            [
                "L-1001",
                datetime(2025, 11, 12),
                datetime(2025, 11, 14),
                1240.0,
                "Sediment core liners",
                "55016 Lab Instruments and Supplies",
                "Example Lab Supply Co.",
                "INV-1001",
                None,
            ],
            [
                "L-1002",
                "2026-02-20",
                "2026-02-24",
                "2180.00",
                "Sediment DNA sequencing run 7",
                "59009 Recharge-Other Expenses",
                "Example Sequencing Core",
                "SEQ-0207",
                None,
            ],
        ]
    )
    result = _read(content)
    assert result.charges == EXPECTED_SAMPLE
    assert result.rejected == []


def test_columns_in_any_order_and_optional_columns_left_out():
    content = "\n".join(
        [
            "Account,Amount,Description,Posting_Date,Transaction_Date,Line_ID,Notes",
            "59009 Recharge-Other Expenses,-2180.00,Reversal of run 7,2026-03-02,2026-03-01,"
            "L-1003,ignored",
        ]
    )
    result = _read(content)
    assert result.rejected == []
    [charge] = result.charges
    assert charge.ledger_line_id == "L-1003"
    assert charge.amount_cents == -218000
    assert charge.vendor is None and charge.reference is None and charge.original_line_id is None


def test_empty_optional_cells_are_missing_and_original_line_id_is_read():
    content = HEADER + "\nL-1003,2026-03-01,2026-03-02,-2180,Reversal,59009,  ,,L-1002\n"
    [charge] = _read(content).charges
    assert charge.vendor is None
    assert charge.reference is None
    assert charge.original_line_id == "L-1002"
    assert charge.amount_cents == -218000


@pytest.mark.parametrize(
    ("amount", "cents"),
    [("1240", 124000), ("1240.5", 124050), ("0.01", 1), ("-0.10", -10), ("0", 0)],
)
def test_amounts_become_integer_cents(amount: str, cents: int):
    content = HEADER + f"\nL-1,2025-01-01,2025-01-02,{amount},Thing,55016,,,\n"
    [charge] = _read(content).charges
    assert charge.amount_cents == cents


def test_missing_required_columns_rejects_the_file():
    content = "line_id,transaction_date,amount,description\nL-1,2025-01-01,1.00,Thing\n"
    with pytest.raises(LedgerFileError, match="posting_date, account"):
        _read(content)


def test_empty_file_is_rejected():
    with pytest.raises(LedgerFileError, match="empty"):
        _read(b"")


def test_column_named_twice_rejects_the_file():
    with pytest.raises(LedgerFileError, match="amount twice"):
        _read(HEADER + ",amount\n")


def test_non_utf8_file_is_rejected():
    with pytest.raises(LedgerFileError):
        _read(b"\xff\xfe\x00\x81garbage")


def test_bad_rows_are_rejected_with_row_number_and_reason_and_the_rest_load():
    content = "\n".join(
        [
            HEADER,
            "L-1,2025-01-01,2025-01-02,10.00,Good,55016,,,",
            "L-2,2025-01-01,2025-01-02,12.345,Too many decimals,55016,,,",
            "L-3,2025-01-01,2025-01-02,$10.00,Dollar sign,55016,,,",
            "L-4,01/02/2025,2025-01-02,10.00,Wrong date format,55016,,,",
            "L-5,2025-02-30,2025-01-02,10.00,Not a real date,55016,,,",
            ",2025-01-01,2025-01-02,10.00,No line ID,55016,,,",
            "L-6,2025-01-01,,ten,,,,,",
            "",
            "L-7,2025-01-01,2025-01-02,1e3,Exponent,55016,,,",
            "L-8,2025-01-01,2025-01-02,20.00,Also good,55016,,,",
        ]
    )
    result = _read(content)
    assert [c.ledger_line_id for c in result.charges] == ["L-1", "L-8"]
    assert [r.row for r in result.rejected] == [3, 4, 5, 6, 7, 8, 10]
    reasons = {r.row: r.reason for r in result.rejected}
    assert "amount '12.345'" in reasons[3]
    assert "amount '$10.00'" in reasons[4]
    assert "transaction_date '01/02/2025' isn't a date written as YYYY-MM-DD" in reasons[5]
    assert "isn't a real date" in reasons[6]
    assert reasons[7] == "line_id is empty."
    assert reasons[8] == (
        "posting_date is empty. amount 'ten' isn't dollars with up to two decimals, such as "
        "-1240.00. description is empty. account is empty."
    )
    assert "amount '1e3'" in reasons[10]


def test_excel_amount_with_more_than_two_decimals_is_rejected():
    content = _xlsx(
        [
            HEADER.split(","),
            ["L-1", "2025-01-01", "2025-01-02", 10.125, "Thing", "55016"],
            [1001, "2025-01-01", "2025-01-02", 10.1, "Numeric line ID", "55016"],
        ]
    )
    result = _read(content)
    assert result.rejected == [
        RejectedRow(
            row=2, reason="amount '10.125' isn't dollars with up to two decimals, such as -1240.00."
        )
    ]
    [charge] = result.charges
    assert charge.ledger_line_id == "1001"
    assert charge.amount_cents == 1010


def test_excel_date_with_time_of_day_is_rejected():
    content = _xlsx(
        [HEADER.split(","), ["L-1", datetime(2025, 1, 1, 9, 30), "2025-01-02", 1, "T", "55016"]]
    )
    [rejected] = _read(content).rejected
    assert rejected.row == 2
    assert "transaction_date has a time of day" in rejected.reason


def test_lines_already_on_file_are_skipped():
    result = _read(SAMPLE_CSV, existing=("L-1001",))
    assert result.skipped_line_ids == ["L-1001"]
    assert [c.ledger_line_id for c in result.charges] == ["L-1002"]
    assert result.rejected == []


def test_uploading_the_same_file_again_adds_nothing():
    result = _read(SAMPLE_CSV, existing=("L-1001", "L-1002"))
    assert result.charges == []
    assert result.skipped_line_ids == ["L-1001", "L-1002"]


def test_duplicate_line_id_in_the_same_file_keeps_the_first_and_rejects_the_rest():
    content = "\n".join(
        [
            HEADER,
            "L-1,2025-01-01,2025-01-02,10.00,First,55016,,,",
            "L-1,2025-01-01,2025-01-02,99.00,Second,55016,,,",
        ]
    )
    result = _read(content)
    assert [c.description for c in result.charges] == ["First"]
    assert result.rejected == [
        RejectedRow(row=3, reason="line_id L-1 already appears in this file at row 2.")
    ]


def test_header_only_file_reads_nothing():
    result = _read(HEADER + "\n")
    assert result.charges == [] and result.skipped_line_ids == [] and result.rejected == []


def test_golden_ledger_file_matches_the_sample_grants_charges():
    sample = load_sample_grant()
    line_ids = iter(c.id for c in sample.charges)
    result = read_ledger_file(
        LEDGER_FILE.read_bytes(),
        workspace_id=sample.workspace.id,
        grant_id=sample.grant.id,
        existing_line_ids=(),
        now=BEFORE_ANY_POSTING,
        new_id=lambda: next(line_ids),
    )
    assert result.rejected == []
    assert tuple(result.charges) == sample.charges


def test_line_arrives_at_start_of_posting_date_when_that_is_still_ahead_of_now():
    now = datetime(2025, 11, 13, 23, 59, tzinfo=UTC)
    [first, second] = _read(SAMPLE_CSV, now=now).charges
    assert first.arrived_at == datetime(2025, 11, 14, tzinfo=UTC)
    assert second.arrived_at == datetime(2026, 2, 24, tzinfo=UTC)


def test_line_arrives_now_when_its_posting_date_has_already_begun():
    now = datetime(2025, 12, 1, 9, 30, tzinfo=UTC)
    [first, second] = _read(SAMPLE_CSV, now=now).charges
    assert first.arrived_at == now
    assert second.arrived_at == datetime(2026, 2, 24, tzinfo=UTC)


def test_line_posted_on_todays_date_arrives_now():
    now = datetime(2025, 11, 14, 12, 0, tzinfo=UTC)
    [first, _] = _read(SAMPLE_CSV, now=now).charges
    assert first.arrived_at == now


def test_now_in_another_timezone_is_converted_to_utc():
    pacific = timezone(timedelta(hours=-8))
    now = datetime(2025, 11, 13, 20, 0, tzinfo=pacific)  # 04:00 UTC on November 14
    [first, _] = _read(SAMPLE_CSV, now=now).charges
    assert first.arrived_at == datetime(2025, 11, 14, 4, 0, tzinfo=UTC)
    assert first.arrived_at.tzinfo == UTC


def test_now_without_a_timezone_is_refused():
    with pytest.raises(ValueError, match="timezone-aware"):
        _read(SAMPLE_CSV, now=datetime(2025, 11, 14))
