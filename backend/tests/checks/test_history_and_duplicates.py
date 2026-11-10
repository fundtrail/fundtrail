"""The status history line, and the search for bills that look like the same one."""

from datetime import UTC, date, datetime

from app.checks.duplicates import likely_duplicates
from app.checks.history import history_line
from app.checks.run import run_checks
from app.contracts.checks import ChargeStatus, ChecksInput, StatusEntry
from app.contracts.fixtures import load_sample_grant
from app.contracts.runs import Trigger, TriggerKind

from .grant_builder import Grant, at, cited

# The status history line.


def _sample_status(now: datetime, charge_id: str) -> ChargeStatus:
    s = load_sample_grant()
    out = run_checks(
        ChecksInput(
            now=now,
            charges=tuple(c for c in s.charges if c.arrived_at <= now),
            files=tuple(f for f in s.files if f.arrived_at <= now),
            records=tuple(r for r in s.records if r.written_at <= now),
        )
    )
    return next(c for c in out.charges if c.charge_id == charge_id)


def test_the_extension_confirmation_reads_as_the_docs_example() -> None:
    s = load_sample_grant()
    before_time = datetime(2026, 2, 24, 12, tzinfo=UTC)
    after_time = datetime(2026, 4, 10, 16, tzinfo=UTC)
    confirmation = next(r for r in s.records if r.id == "rec-confirm-extension")
    before = StatusEntry(
        changed_at=before_time,
        trigger=Trigger(kind=TriggerKind.CHARGE, id="chg-l-1002"),
        status=_sample_status(before_time, "chg-l-1002"),
    )
    after = StatusEntry(
        changed_at=after_time,
        trigger=Trigger(kind=TriggerKind.RECORD, id=confirmation.id),
        status=_sample_status(after_time, "chg-l-1002"),
    )
    line = history_line(after, before, confirmation, s.records)
    assert line == "Apr 10, 2026 · new end date confirmed · Possible conflict → Evidence complete"


def test_a_charge_arriving_reads_with_its_ledger_line_and_no_earlier_state() -> None:
    s = load_sample_grant()
    when = datetime(2026, 2, 24, 12, tzinfo=UTC)
    charge = next(c for c in s.charges if c.id == "chg-l-1002")
    entry = StatusEntry(
        changed_at=when,
        trigger=Trigger(kind=TriggerKind.CHARGE, id=charge.id),
        status=_sample_status(when, charge.id),
    )
    assert history_line(entry, None, charge) == (
        "Feb 24, 2026 · ledger line L-1002 arrived · Possible conflict"
    )


def test_a_file_the_clock_and_a_record_problem_read_plainly() -> None:
    s = load_sample_grant()
    f = next(f for f in s.files if f.id == "file-extension-notice")
    when = datetime(2026, 4, 9, 16, tzinfo=UTC)
    status = _sample_status(when, "chg-l-1002")
    entry = StatusEntry(
        changed_at=when, trigger=Trigger(kind=TriggerKind.FILE, id=f.id), status=status
    )
    assert (
        history_line(entry, entry, f)
        == "Apr 9, 2026 · extension_notice.txt arrived · Possible conflict"
    )
    clock = StatusEntry(changed_at=when, trigger=Trigger(kind=TriggerKind.CLOCK), status=status)
    assert history_line(clock) == "Apr 9, 2026 · time passed · Possible conflict"


# The likely-duplicate search.


def _bill(g: Grant, f: str, total: int, when: datetime, **kw: object) -> str:
    data: dict[str, object] = {"kind": "bill", "total": cited(total, f"${total / 100:,.2f}", f)}
    if "number" in kw:
        data["document_number"] = cited(kw["number"], file_id=f)
    if "vendor" in kw:
        data["vendor"] = cited(kw["vendor"], file_id=f)
    if "dated" in kw:
        data["dated"] = cited(kw["dated"], file_id=f)
    return g.agent(data, when)


def test_the_same_document_number_is_a_likely_duplicate_whatever_else_differs() -> None:
    g = Grant()
    g.file("f-pdf", at(2024, 3, 1))
    g.file("f-photo", at(2024, 3, 5))
    old = _bill(g, "f-pdf", 124000, at(2024, 3, 1), number="INV-1001")
    new = _bill(g, "f-photo", 124500, at(2024, 3, 5), number="inv 1001")
    new_record = g.records.pop()
    assert likely_duplicates(new_record, g.records, g.files) == [old]
    assert new == new_record.id


def test_the_exact_same_file_bytes_are_a_likely_duplicate() -> None:
    g = Grant()
    g.file("f-a", at(2024, 3, 1), sha="same")
    g.file("f-b", at(2024, 3, 5), sha="same")
    old = _bill(g, "f-a", 10000, at(2024, 3, 1))
    _bill(g, "f-b", 99999, at(2024, 3, 5))
    assert likely_duplicates(g.records.pop(), g.records, g.files) == [old]


def test_the_same_total_needs_the_same_vendor_or_a_close_date_and_nothing_disagreeing() -> None:
    g = Grant()
    for i in range(6):
        g.file(f"f{i}", at(2024, 3, 1))
    match = _bill(g, "f0", 40000, at(2024, 3, 1), vendor="Example Facility", dated=date(2024, 3, 1))
    _bill(g, "f1", 40000, at(2024, 3, 1), vendor="Other Vendor")  # vendor disagrees
    _bill(
        g, "f2", 40000, at(2024, 3, 1), vendor="Example Facility", dated=date(2024, 2, 1)
    )  # a month
    _bill(g, "f3", 40000, at(2024, 3, 1))  # nothing agrees
    _bill(g, "f4", 41000, at(2024, 3, 1), vendor="Example Facility")  # another total
    new = _bill(g, "f5", 40000, at(2024, 3, 2), vendor="EXAMPLE FACILITY", dated=date(2024, 3, 8))
    new_record = g.records.pop()
    assert new_record.id == new
    assert likely_duplicates(new_record, g.records, g.files) == [match]


def test_the_same_file_a_confirmed_copy_and_a_non_bill_are_left_out() -> None:
    g = Grant()
    g.file("f-a", at(2024, 3, 1))
    g.file("f-b", at(2024, 3, 2))
    _bill(g, "f-a", 10000, at(2024, 3, 1), number="A-1")
    copy = _bill(g, "f-b", 10000, at(2024, 3, 2), number="A-1")
    mark = g.agent(
        {"kind": "duplicate", "copy_file_id": "f-b", "original_file_id": "f-a"}, at(2024, 3, 2)
    )
    g.confirm(mark, when=at(2024, 3, 3))
    same_file = _bill(g, "f-a", 10000, at(2024, 3, 4), number="A-1")
    found = likely_duplicates(g.records.pop(), g.records, g.files)
    assert copy not in found and same_file not in found
    assert found == []  # the only other bill is in the same file


def test_the_list_is_short() -> None:
    g = Grant()
    for i in range(8):
        g.file(f"f{i}", at(2024, 3, 1))
        _bill(g, f"f{i}", 10000, at(2024, 3, 1), number="X-9")
    g.file("f-new", at(2024, 3, 2))
    _bill(g, "f-new", 10000, at(2024, 3, 2), number="X-9")
    assert len(likely_duplicates(g.records.pop(), g.records, g.files)) == 5
