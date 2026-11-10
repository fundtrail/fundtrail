"""A small builder for the checks tests: one synthetic grant, its terms, files, charges and records.

Everything here is synthetic. Award numbers start with SYN- and addresses use .example.
"""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from app.checks.ledger_accounts import ODC_OTHER
from app.checks.run import run_checks
from app.contracts.charges import Charge
from app.contracts.checks import ChargeStatus, ChecksInput, ChecksOutput, Reason
from app.contracts.evidence import EvidenceFile
from app.contracts.records import Record
from app.contracts.runs import AgentRun

ACCOUNTANT = "00000000-0000-4000-8000-0000000000aa"
SUPPLIES = "55016 Lab Instruments and Supplies"
RECHARGE = "59009 Recharge-Other Expenses"
STIPENDS = "56712 Participant Support-Stipends"
TRAVEL = "57211 In-State Travel - Air Fare"
SALARY = "51200 Staff Salaries & Wages"
BENEFITS = "53100 OASDI"
NO_GROUP = "99999 Not In Any Group"

PO_EMAIL = "po@funder.example"
PI_EMAIL = "pi@university.example"


def at(y: int, m: int, d: int, h: int = 12) -> datetime:
    return datetime(y, m, d, h, tzinfo=UTC)


def cited(
    value: Any, text: str | None = None, file_id: str = "f-letter", match: str = "exact"
) -> dict[str, Any]:
    text = text if text is not None else str(value)
    return {
        "value": value,
        "text": text,
        "citation": {
            "file_id": file_id,
            "passage": text,
            "location": {
                "type": "char_location",
                "start_char_index": 0,
                "end_char_index": len(text),
            },
            "match": match,
        },
    }


class Grant:
    def __init__(self, grant_id: str = "g1"):
        self.grant_id = grant_id
        self.records: list[Record] = []
        self.files: list[EvidenceFile] = []
        self.charges: list[Charge] = []
        self.failed_runs: list[AgentRun] = []
        self._n = 0
        self.file("f-letter", at(2023, 1, 12))

    # Things that arrive.

    def file(
        self,
        id: str,
        arrived: datetime,
        sha: str | None = None,
        media_type: str = "text/plain",
        source: str = "upload",
    ) -> str:
        name = f"{id}.txt"
        self.files.append(
            EvidenceFile.model_validate(
                {
                    "id": id,
                    "workspace_id": "w",
                    "grant_id": self.grant_id,
                    "source": source,
                    "name": name,
                    "media_type": media_type,
                    "storage_path": f"w/{self.grant_id}/{id}/{name}",
                    "sha256": sha or f"sha-{id}",
                    "arrived_at": arrived,
                }
            )
        )
        return id

    def charge(
        self,
        id: str,
        cost_date: date,
        amount: int,
        account: str = SUPPLIES,
        vendor: str | None = "Example Lab Supply Co.",
        posted: date | None = None,
        original_line_id: str | None = None,
    ) -> str:
        posted = posted or cost_date
        self.charges.append(
            Charge(
                id=id,
                workspace_id="w",
                grant_id=self.grant_id,
                ledger_line_id=f"L-{id}",
                transaction_date=cost_date,
                posting_date=posted,
                arrived_at=datetime(posted.year, posted.month, posted.day, tzinfo=UTC),
                amount_cents=amount,
                description="Synthetic charge",
                account=account,
                vendor=vendor,
                original_line_id=original_line_id,
            )
        )
        return id

    # Records.

    def add(
        self,
        author: str,
        data: dict[str, Any],
        when: datetime,
        replaces: str | None = None,
        id: str | None = None,
    ) -> str:
        self._n += 1
        rid = id or f"r{self._n}"
        self.records.append(
            Record.model_validate(
                {
                    "id": rid,
                    "workspace_id": "w",
                    "grant_id": self.grant_id,
                    "author": author,
                    "author_user_id": ACCOUNTANT if author == "user" else None,
                    "written_at": when,
                    "replaces_id": replaces,
                    "data": data,
                }
            )
        )
        return rid

    def agent(self, data: dict[str, Any], when: datetime, replaces: str | None = None) -> str:
        return self.add("agent", data, when, replaces)

    def user(self, data: dict[str, Any], when: datetime, replaces: str | None = None) -> str:
        return self.add("user", data, when, replaces)

    def confirm(self, *ids: str, when: datetime, decision: str = "confirmed") -> str:
        return self.user(
            {"kind": "confirmation", "record_ids": list(ids), "decision": decision}, when
        )

    # Terms, written by the agent from the award letter.

    def period(
        self, start: date | None, end: date, dated: date, when: datetime, f: str = "f-letter"
    ) -> str:
        data: dict[str, Any] = {
            "kind": "period_of_performance",
            "dated": cited(dated, file_id=f),
            "end": cited(end, file_id=f),
        }
        if start is not None:
            data["start"] = cited(start, file_id=f)
        return self.agent(data, when)

    def budget_line(
        self,
        name: str,
        amount: int,
        category: str,
        when: datetime,
        dated: date = date(2023, 1, 10),
        f: str = "f-letter",
    ) -> str:
        return self.agent(
            {
                "kind": "budget_line",
                "dated": cited(dated, file_id=f),
                "name": cited(name, file_id=f),
                "amount": cited(amount, f"${amount // 100:,}", f),
                "category": category,
            },
            when,
        )

    def person(self, name: str, email: str, role: str, when: datetime) -> str:
        return self.agent(
            {
                "kind": "person",
                "dated": cited(date(2023, 1, 10)),
                "name": cited(name),
                "email": cited(email),
                "role": cited(role),
            },
            when,
        )

    def approval_rule(
        self,
        applies_to: str,
        approver: str,
        channel: str | None,
        when: datetime,
        scope: str | None = None,
    ) -> str:
        data: dict[str, Any] = {
            "kind": "approval_rule",
            "dated": cited(date(2023, 1, 10)),
            "applies_to": cited(applies_to),
            "approver": cited(approver),
        }
        if channel:
            data["channel"] = cited(channel)
        if scope is not None:  # every_charge or moved_out, once #39 adds it
            data["scope"] = scope
        return self.agent(data, when)

    def notice(
        self,
        number: str,
        by: int | None,
        to_date: int | None,
        when: datetime,
        dated: date = date(2023, 1, 10),
    ) -> str:
        data: dict[str, Any] = {
            "kind": "notice",
            "dated": cited(dated),
            "amendment_number": cited(number),
            "amendment_type": cited("New Project" if number == "000" else "Increment"),
        }
        if by is not None:
            data["obligated_by_amendment"] = cited(by, f"${by // 100:,}")
        if to_date is not None:
            data["obligated_to_date"] = cited(to_date, f"${to_date // 100:,}")
        return self.agent(data, when)

    def standard_terms(self, confirm: bool = True, with_rule: bool = True) -> dict[str, str]:
        """A grant from Feb 1, 2023 to Jan 31, 2026, like the sample grant.

        The agent writes the terms, and the accountant confirms them on Jan 12, 2023.
        """
        when = at(2023, 1, 12, 15)
        ids = {
            "period": self.period(date(2023, 2, 1), date(2026, 1, 31), date(2023, 1, 10), when),
            "psc": self.budget_line(
                "Participant Support Costs", 2_000_000, "participant_support", when
            ),
            "odc": self.budget_line("Other Direct Costs", 10_000_000, "other_direct_costs", when),
            "ms": self.budget_line(
                "Materials and Supplies", 4_000_000, "materials_and_supplies", when
            ),
            "other": self.budget_line("Other", 6_000_000, ODC_OTHER.value, when),
            "pi": self.person("Dr. Robin Example", PI_EMAIL, "Principal Investigator", when),
            "po": self.person("Dr. Jesse Sample", PO_EMAIL, "Program Officer", when),
            "notice": self.notice("000", 12_000_000, 12_000_000, when),
        }
        if with_rule:
            ids["rule"] = self.approval_rule(
                "Participant Support Costs", "Program Officer", "Research.gov", when
            )
        if confirm:
            ids["confirm"] = self.confirm(*ids.values(), when=at(2023, 1, 12, 16))
        return ids

    # Facts, links and answers.

    def bill(
        self, total: int, f: str, when: datetime, match: str = "exact", number: str | None = None
    ) -> str:
        data: dict[str, Any] = {
            "kind": "bill",
            "total": cited(total, f"${total / 100:,.2f}", f, match),
        }
        if number:
            data["document_number"] = cited(number, file_id=f)
        return self.agent(data, when)

    def approval(
        self,
        f: str,
        when: datetime,
        email: str = PO_EMAIL,
        on: date | None = date(2024, 5, 1),
        channel: str | None = "Research.gov",
    ) -> str:
        data: dict[str, Any] = {
            "kind": "approval",
            "approver_email": cited(email, file_id=f),
            "covers": cited("participant stipends", file_id=f),
        }
        if on is not None:
            data["approved_on"] = cited(on, file_id=f)
        if channel is not None:
            data["channel"] = cited(channel, file_id=f)
        return self.agent(data, when)

    def note(
        self, f: str, when: datetime, start: date | None = None, end: date | None = None
    ) -> str:
        data: dict[str, Any] = {
            "kind": "note",
            "label": "Effort report",
            "statement": cited("Certified", file_id=f),
        }
        if start and end:
            data["period"] = {"start": cited(start, file_id=f), "end": cited(end, file_id=f)}
        return self.agent(data, when)

    def link(
        self,
        record_id: str,
        charge_id: str,
        when: datetime,
        amount: int | None = None,
        default: str | None = None,
        item: str | None = None,
        author: str = "agent",
        replaces: str | None = None,
    ) -> str:
        f = next(c.file_id for r in self.records if r.id == record_id for c in _citations(r))
        data: dict[str, Any] = {
            "kind": "link",
            "record_id": record_id,
            "charge_id": charge_id,
            "amount_cents": amount,
            "part": cited(0, "x", f)["citation"],
        }
        if default:
            data["default_item"] = default
        if item:
            data["item_record_id"] = item
        return self.add(author, data, when, replaces)

    def assign(self, charge_id: str, line_id: str, when: datetime) -> str:
        return self.agent(
            {
                "kind": "budget_assignment",
                "charge_id": charge_id,
                "record_id": line_id,
                "reason": "Synthetic.",
            },
            when,
        )

    def answer(
        self,
        charge_id: str | None,
        answer: str,
        when: datetime,
        question: str = "allowable",
        record_id: str | None = None,
        rests_on: Sequence[str] = (),
        author: str = "agent",
        replaces: str | None = None,
        file_id: str | None = None,
        rule: str | None = None,
    ) -> str:
        data: dict[str, Any] = {
            "kind": "judgment",
            "charge_id": charge_id,
            "question": question,
            "record_id": record_id,
            "file_id": file_id,
            "text": "A question",
            "answer": answer,
            "reasoning": "Synthetic reasoning.",
            "rests_on": list(rests_on),
            "rule": rule,
        }
        return self.add(author, data, when, replaces)

    def item(
        self, charge_id: str, needed: str, when: datetime, author: str = "agent", **fields: Any
    ) -> str:
        return self.add(
            author,
            {"kind": "checklist_item", "charge_id": charge_id, "needed": needed, **fields},
            when,
        )

    def confirmed_line(self, name: str, category: str, when: datetime) -> str:
        """A budget line the agent read and the accountant confirmed."""
        line = self.budget_line(name, 1_000_000, category, when)
        self.confirm(line, when=when)
        return line

    def supplies_charge(
        self, id: str, cost_date: date, amount: int, when: datetime, **kw: Any
    ) -> str:
        """A supplies charge with its invoice linked, assigned to a line, answered supports."""
        line = kw.pop("line")
        self.charge(id, cost_date, amount, **kw)
        f = self.file(f"f-{id}", when)
        b = self.bill(amount, f, when)
        self.link(b, id, when, amount=amount, default="bill")
        self.assign(id, line, when)
        self.answer(id, "supports", when, rests_on=[b])
        return b

    # Running the checks.

    def run(self, now: datetime) -> ChecksOutput:
        return run_checks(
            ChecksInput(
                now=now,
                charges=tuple(c for c in self.charges if c.arrived_at <= now),
                files=tuple(f for f in self.files if f.arrived_at <= now),
                records=tuple(r for r in self.records if r.written_at <= now),
                failed_runs=tuple(self.failed_runs),
            )
        )

    def status(self, charge_id: str, now: datetime) -> ChargeStatus:
        return next(c for c in self.run(now).charges if c.charge_id == charge_id)


def _citations(r: Record):  # type: ignore[no-untyped-def]
    from app.contracts.records import citations

    return citations(r.data)


def failing(status: ChargeStatus) -> list[Reason]:
    return [r for r in status.reasons if r.bucket != "evidence_complete"]


def problems(status: ChargeStatus) -> set[tuple[str, str]]:
    return {(r.check, r.problem) for r in failing(status)}
