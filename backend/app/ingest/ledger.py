"""Read a grant's ledger file (CSV or Excel) into charges.

Follows docs/contracts.md section 13 (the file) and section 6 (the charge), and decision 0023
for when a line arrives. This is a pure function: it never touches the database. Storing the
charges it returns is the API's job.
"""

import csv
import io
import re
import uuid
import zipfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal

from pydantic import ValidationError

from app.contracts.charges import Charge, LedgerRow

REQUIRED_COLUMNS = (
    "line_id",
    "transaction_date",
    "posting_date",
    "amount",
    "description",
    "account",
)
OPTIONAL_COLUMNS = ("vendor", "reference", "original_line_id")
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# Only ASCII digits: `\d` would also accept digits from other scripts, such as Arabic-Indic.
_AMOUNT_PATTERN = re.compile(r"-?[0-9]+(\.[0-9]{1,2})?")
_DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_XLSX_MAGIC = b"PK\x03\x04"

type Cell = str | int | float | Decimal | date | datetime | bool | None


@dataclass(frozen=True)
class RejectedRow:
    """A row that couldn't be read. `row` is the spreadsheet row number; the header is row 1."""

    row: int
    reason: str


@dataclass(frozen=True)
class LedgerReadResult:
    charges: list[Charge] = field(default_factory=list)
    skipped_line_ids: list[str] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)


class LedgerFileError(ValueError):
    """The whole file can't be read: not CSV or Excel, no header, or a required column missing."""


class _RowError(ValueError):
    pass


def read_ledger_file(
    content: bytes,
    *,
    workspace_id: str,
    grant_id: str,
    existing_line_ids: Iterable[str],
    now: datetime,
    new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
) -> LedgerReadResult:
    """Read a ledger file's bytes into new charges, skipped line IDs and rejected rows.

    A row whose `line_id` is already on file is skipped. A row that can't be read is rejected
    with its row number and a plain reason, and the rest still load. Raises `LedgerFileError`
    when the file as a whole can't be read.

    `now` is the workspace's "now". A line arrives at 00:00 UTC on its posting date if that's
    still ahead of `now`, and otherwise at `now` (decision 0023).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware.")
    now = now.astimezone(UTC)
    rows = _xlsx_rows(content) if content.startswith(_XLSX_MAGIC) else _csv_rows(content)
    header_row = next(rows, None)
    if header_row is None:
        raise LedgerFileError("The file is empty. The first row must be a header.")
    columns = _read_header(header_row)

    on_file = set(existing_line_ids)
    first_seen_at: dict[str, int] = {}
    charges: list[Charge] = []
    skipped: list[str] = []
    rejected: list[RejectedRow] = []

    for row_number, cells in enumerate(rows, start=2):
        values = {name: _text(cells[i]) if i < len(cells) else None for name, i in columns.items()}
        if all(v is None for v in values.values()):
            continue  # A blank row, such as a trailing line, isn't a ledger line.
        try:
            line_id = _required(values, "line_id")
            if line_id in on_file:
                skipped.append(line_id)
                continue
            if line_id in first_seen_at:
                raise _RowError(
                    f"line_id {line_id} already appears in this file at row "
                    f"{first_seen_at[line_id]}."
                )
            first_seen_at[line_id] = row_number
            charges.append(
                _build_charge(values, cells, columns, workspace_id, grant_id, now, new_id)
            )
        except _RowError as error:
            rejected.append(RejectedRow(row=row_number, reason=str(error)))

    return LedgerReadResult(charges=charges, skipped_line_ids=skipped, rejected=rejected)


def _build_charge(
    values: dict[str, str | None],
    cells: Sequence[Cell],
    columns: dict[str, int],
    workspace_id: str,
    grant_id: str,
    now: datetime,
    new_id: Callable[[], str],
) -> Charge:
    problems: list[str] = []

    def attempt[T](read: Callable[[], T]) -> T | None:
        try:
            return read()
        except _RowError as error:
            problems.append(str(error))
            return None

    def raw(name: str) -> Cell:
        i = columns.get(name)
        return cells[i] if i is not None and i < len(cells) else None

    transaction_date = attempt(lambda: _date(raw("transaction_date"), "transaction_date"))
    posting_date = attempt(lambda: _date(raw("posting_date"), "posting_date"))
    amount = attempt(lambda: _dollars(raw("amount")))
    description = attempt(lambda: _required(values, "description"))
    account = attempt(lambda: _required(values, "account"))
    if problems:
        raise _RowError(" ".join(problems))
    assert transaction_date and posting_date and amount is not None
    assert description and account

    try:
        row = LedgerRow(
            line_id=_required(values, "line_id"),
            transaction_date=transaction_date,
            posting_date=posting_date,
            amount=amount,
            description=description,
            account=account,
            vendor=values.get("vendor"),
            reference=values.get("reference"),
            original_line_id=values.get("original_line_id"),
        )
    except ValidationError as error:
        raise _RowError(
            " ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}." for e in error.errors())
        ) from error
    # The contract maps a row to its charge. Decision 0023 then moves the arrival to `now`
    # when the posting date has already begun.
    charge = row.to_charge(id=new_id(), workspace_id=workspace_id, grant_id=grant_id)
    if now > charge.arrived_at:
        charge = charge.model_copy(update={"arrived_at": now})
    return charge


def _read_header(cells: Sequence[Cell]) -> dict[str, int]:
    columns: dict[str, int] = {}
    for i, cell in enumerate(cells):
        name = (_text(cell) or "").lower()
        if name not in KNOWN_COLUMNS:
            continue  # Columns FundTrail doesn't use are ignored.
        if name in columns:
            raise LedgerFileError(f"The header names the column {name} twice.")
        columns[name] = i
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise LedgerFileError("The header is missing required columns: " + ", ".join(missing) + ".")
    return columns


def _csv_rows(content: bytes) -> Iterator[list[Cell]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise LedgerFileError("The file isn't an Excel file or a UTF-8 CSV file.") from error
    try:
        rows: list[list[Cell]] = [list(row) for row in csv.reader(io.StringIO(text, newline=""))]
    except csv.Error as error:
        raise LedgerFileError(f"The CSV file can't be read: {error}.") from error
    return iter(rows)


def _xlsx_rows(content: bytes) -> Iterator[list[Cell]]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, OSError, ValueError) as error:
        raise LedgerFileError("The Excel file can't be read.") from error
    try:
        sheet = workbook.worksheets[0]
        # Read-only mode trusts the size the sheet says it has, which can be wrong and would
        # drop rows or columns. Reset it so every stored cell is read.
        sheet.reset_dimensions()
        rows = [[_cell(value) for value in row] for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()
    return iter(rows)


def _cell(value: object) -> Cell:
    """An Excel cell's value, with anything unusual (a time, rich text) kept as its text."""
    if value is None or isinstance(value, str | int | float | Decimal | date | bool):
        return value
    return str(value)


def _text(cell: Cell) -> str | None:
    """A cell as text, or None when it's empty."""
    if cell is None:
        return None
    if isinstance(cell, float) and cell.is_integer():
        cell = int(cell)  # Excel stores 1001 as 1001.0.
    if isinstance(cell, datetime):
        cell = cell.date() if cell.time() == time(0, 0) else cell
    text = cell.isoformat() if isinstance(cell, date) else str(cell)
    text = text.strip()
    return text or None


def _required(values: dict[str, str | None], name: str) -> str:
    value = values.get(name)
    if value is None:
        raise _RowError(f"{name} is empty.")
    return value


def _date(cell: Cell, name: str) -> date:
    if isinstance(cell, datetime):
        if cell.time() != time(0, 0):
            raise _RowError(f"{name} has a time of day; it should be a date only.")
        return cell.date()
    if isinstance(cell, date):
        return cell
    text = _text(cell)
    if text is None:
        raise _RowError(f"{name} is empty.")
    if not _DATE_PATTERN.fullmatch(text):
        raise _RowError(f"{name} {text!r} isn't a date written as YYYY-MM-DD.")
    try:
        return date.fromisoformat(text)
    except ValueError as error:
        raise _RowError(f"{name} {text!r} isn't a real date.") from error


def _dollars(cell: Cell) -> Decimal:
    if isinstance(cell, bool):
        raise _RowError(f"amount {cell!r} isn't a number.")
    if isinstance(cell, float):
        text = repr(cell)  # The shortest form that reads back as the same number.
        if "e" in text.lower():
            raise _RowError(f"amount {cell!r} isn't dollars with up to two decimals.")
    else:
        text = _text(cell)
    if text is None:
        raise _RowError("amount is empty.")
    if not _AMOUNT_PATTERN.fullmatch(text):
        raise _RowError(f"amount {text!r} isn't dollars with up to two decimals, such as -1240.00.")
    return Decimal(text)
