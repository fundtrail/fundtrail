"""The seven sections of the evidence report (decision 0022), as plain blocks.

Everything here selects, groups, counts and formats. Buckets, reasons, status
text, what's in force and what counts all come from the inputs: the checks'
output, rules.RecordState and the stand-ins in pending.py. Nothing here decides
a bucket, a reason, whether something is open, or which term is in force.
"""

from collections import Counter
from collections.abc import Iterable

from app.checks.findings import BUDGET
from app.checks.history import describe_trigger
from app.contracts.api import RecordState as TermState
from app.contracts.api import TermView
from app.contracts.charges import Charge
from app.contracts.checks import (
    Bucket,
    ChargeStatus,
    ChecklistEntry,
    ItemSource,
    Reason,
    StatusEntry,
    ready_for_closeout,
)
from app.contracts.evidence import EvidenceFile
from app.contracts.mail import HoldReason
from app.contracts.records import (
    FACT_KINDS,
    TERM_KINDS,
    AcceptedReason,
    Answer,
    Approval,
    ApprovalRule,
    Author,
    Bill,
    BudgetAssignment,
    BudgetLine,
    ChecklistItem,
    ChecklistRemoval,
    Citation,
    CitedDate,
    CitedMoney,
    Decision,
    Dispute,
    Duplicate,
    Judgment,
    Link,
    Note,
    Notice,
    OtherTerm,
    Period,
    PeriodOfPerformance,
    Person,
    Rate,
    Record,
    RecordKind,
    Snooze,
    citations,
    cited_values,
)
from app.contracts.rules import RecordState
from app.contracts.runs import TriggerKind

from . import fmt
from .inputs import ReportInputs
from .view import Block, Heading, Para, Quote, ReportView, Section, SignLines, Table

# The checks' grant problem for spending over the award's limit (grant_checks.py).
OVER_LIMIT = "over_limit"

SECTION_TITLES = (
    "1. Summary",
    "2. Open at sign-off",
    "3. Decisions",
    "4. Every charge",
    "5. Each charge in full",
    "6. Sources",
    "7. Sign-off",
)

KIND_LABELS = {
    RecordKind.PERIOD_OF_PERFORMANCE: "Period of performance",
    RecordKind.BUDGET_LINE: "Budget line",
    RecordKind.PERSON: "Person",
    RecordKind.APPROVAL_RULE: "Approval rule",
    RecordKind.RATE: "Rate",
    RecordKind.NOTICE: "Funding notice",
    RecordKind.OTHER_TERM: "Other term",
    RecordKind.BILL: "Bill",
    RecordKind.APPROVAL: "Approval",
    RecordKind.NOTE: "Note",
    RecordKind.LINK: "Link",
    RecordKind.BUDGET_ASSIGNMENT: "Budget line assignment",
    RecordKind.JUDGMENT: "Answer",
    RecordKind.CHECKLIST_ITEM: "Checklist item",
    RecordKind.CHECKLIST_REMOVAL: "Checklist removal",
    RecordKind.DISPUTE: "Dispute",
    RecordKind.DUPLICATE: "Duplicate mark",
    RecordKind.CONFIRMATION: "Confirmation",
    RecordKind.ACCEPTED_REASON: "Accepted reason",
    RecordKind.SNOOZE: "Snooze",
    RecordKind.SIGN_OFF: "Sign-off",
    RecordKind.RETRACTION: "Retraction",
}

HOLD_REASONS = {
    HoldReason.UNKNOWN_SENDER: "Unknown sender",
    HoldReason.UNVERIFIED_SENDER: "Sender not verified",
}

ANSWER_LABELS = {
    Answer.SUPPORTS: "Supports",
    Answer.CONTRADICTS: "Contradicts",
    Answer.UNSURE: "Unsure",
}

ADDED_BY = {
    ItemSource.DEFAULT: "by default",
    ItemSource.RULE: "added by an approval rule",
    ItemSource.AGENT: "added by the agent",
    ItemSource.USER: "added by the accountant",
}


def _sentence(text: str) -> str:
    """Ends text with a period unless it already ends with a stop."""
    return text if text.endswith((".", "!", "?")) else f"{text}."


class _Report:
    def __init__(self, inp: ReportInputs):
        self.inp = inp
        self.state = RecordState(inp.records, inp.files)
        self.current = self.state.current()
        self.by_id = self.state.by_id
        self.files = {f.id: f for f in inp.files}
        self.charges = {c.id: c for c in inp.charges}
        self.status = {s.charge_id: s for s in inp.checks.charges}
        self.messages = {m.id: m for m in inp.thread_messages}
        self.order = self._charge_order()

    # Charges, and how they're grouped.

    def _charge_order(self) -> list[tuple[Charge, bool]]:
        """Every charge with whether it's a correction shown under the charge it corrects."""
        nested = {cid for s in self.inp.checks.charges for cid in s.corrections}
        top = sorted(
            (c for c in self.inp.charges if c.id not in nested),
            key=lambda c: (c.transaction_date, c.ledger_line_id, c.id),
        )
        out: list[tuple[Charge, bool]] = []
        for c in top:
            out.append((c, False))
            out.extend(
                (self.charges[cid], True)
                for cid in self.status[c.id].corrections
                if cid in self.charges
            )
        return out

    def net(self, c: Charge) -> int:
        """The charge's net from the checks; its own amount when nothing is netted into it."""
        n = self.status[c.id].net_cents
        return c.amount_cents if n is None else n

    def history_text(self, e: StatusEntry) -> str:
        """W2's wording of what triggered the change, with code's reason for the new bucket."""
        tid = e.trigger.id or ""
        about = {
            TriggerKind.RECORD: self.by_id.get(tid),
            TriggerKind.CHARGE: self.charges.get(tid),
            TriggerKind.FILE: self.files.get(tid),
            TriggerKind.THREAD_MESSAGE: self.messages.get(tid),
            TriggerKind.CLOCK: None,
        }[e.trigger.kind]
        trigger = describe_trigger(e, about, self.inp.records)
        assert isinstance(e.status, ChargeStatus)
        reason = self.headline_reason(e.status)
        return f"{trigger[:1].upper()}{trigger[1:]}. {reason}" if reason else trigger

    def marks(self, c: Charge) -> str:
        out: list[str] = []
        if self.status[c.id].reversed:
            out.append("Reversed")
        if self.status[c.id].accepted:
            out.append("Accepted")
        if self.status[c.id].snoozed:
            out.append("Snoozed")
        return ", ".join(out)

    def budget_line(self, charge_id: str) -> tuple[str, str]:
        """The name of the charge's assigned budget line, and the assignment's reason."""
        assignments = [
            r.data
            for r in self.current
            if isinstance(r.data, BudgetAssignment) and r.data.charge_id == charge_id
        ]
        if not assignments:
            return "", ""
        a = assignments[-1]
        line = self.state.current_version(a.record_id) or self.by_id.get(a.record_id)
        name = line.data.name.value if line and isinstance(line.data, BudgetLine) else ""
        return name, a.reason

    def line_of(self, charge_id: str | None) -> str:
        c = self.charges.get(charge_id or "")
        return c.ledger_line_id if c else (charge_id or "")

    @staticmethod
    def headline_reason(status: ChargeStatus) -> str:
        """Code's text for the reason that gives the charge its bucket."""
        return next((r.text for r in status.reasons if r.bucket == status.bucket), "")

    # Who and what.

    def who(self, r: Record) -> str:
        if r.author == Author.AGENT:
            return "Agent"
        p = self.inp.preparer
        if r.author_user_id == p.id:
            return p.name or p.email
        return r.author_user_id or "Accountant"

    def file_name(self, file_id: str | None) -> str:
        f = self.files.get(file_id or "")
        return f.name if f else (file_id or "")

    def place(self, c: Citation, value_text: str | None = None) -> str:
        return fmt.place(c, self.files, self.inp.file_texts, value_text)

    def quotes(self, cs: Iterable[Citation]) -> list[Block]:
        out: list[Block] = []
        for c in cs:
            if c.passage is not None:
                out.append(Quote(c.passage, self.place(c)))
            else:
                out.append(Para(f"Cited: {self.place(c)}", "small"))
        return out

    def added_by(self, entry: ChecklistEntry) -> str:
        """Who added a checklist item; for an approval rule's item, the rule (issue 115)."""
        rule = self.by_id.get(entry.rule_id or "")
        if entry.added_by == ItemSource.RULE and rule is not None:
            return f"added by the approval rule {self.describe(rule)}"
        return ADDED_BY[entry.added_by]

    def describe(self, r: Record | None) -> str:
        """One line naming a record by what it says."""
        if r is None:
            return ""
        d = r.data
        label = KIND_LABELS[d.kind]
        if isinstance(d, PeriodOfPerformance):
            start = f"{fmt.day(d.start.value)} to " if d.start else "ends "
            return f"{label}: {start}{fmt.day(d.end.value)}"
        if isinstance(d, BudgetLine):
            return f"{d.name.value}: {fmt.money(d.amount.value)}"
        if isinstance(d, Person):
            email = f", {d.email.value}" if d.email else ""
            return f"{d.name.value}, {d.role.value}{email}"
        if isinstance(d, ApprovalRule):
            via = f", through {d.channel.value}" if d.channel else ""
            return f"{d.applies_to.value}: approved by {d.approver.value}{via}"
        if isinstance(d, Rate):
            return f"{d.name.value}: {d.rate.text or d.rate.value}"
        if isinstance(d, Notice):
            parts = [f"Amendment {d.amendment_number.value}, {d.amendment_type.value}"]
            if d.obligated_by_amendment:
                parts.append(f"adds {fmt.money(d.obligated_by_amendment.value)}")
            if d.obligated_to_date:
                parts.append(f"total obligated {fmt.money(d.obligated_to_date.value)}")
            return ", ".join(parts)
        if isinstance(d, OtherTerm):
            return f"{d.label}: {d.statement.value}"
        if isinstance(d, Bill):
            parts = ["Bill"]
            if d.vendor:
                parts.append(f"from {d.vendor.value}")
            if d.document_number:
                parts.append(d.document_number.value)
            return f"{' '.join(parts)}, total {fmt.money(d.total.value)}"
        if isinstance(d, Approval):
            return f"Approval from {d.approver_email.value}: {d.covers.value}"
        if isinstance(d, Note):
            return f"Note: {d.label}"
        if isinstance(d, ChecklistItem):
            return f"Checklist item: {d.needed}"
        if isinstance(d, Judgment):
            return f"{label}: {d.text}"
        return label

    def decision_stamp(self, r: Record) -> Record:
        """Who decided and when: the accountant's own record, or their confirmation."""
        if r.author == Author.USER:
            return r
        return self.state.decided_by(r.id) or r

    def source_of(self, record_id: str) -> str:
        """The name of the file a term was read from."""
        r = self.by_id.get(record_id)
        cited = next(citations(r.data), None) if r else None
        return self.file_name(cited.file_id) if cited else record_id

    def term_confirmed(self, view: TermView) -> str:
        """Who confirmed a term and when, from the grant page's view of it."""
        r = view.record
        if r.author == Author.USER:
            return f"Entered by {self.who(r)}, {fmt.day(r.written_at)}"
        if view.decision is None:
            return ""
        return f"Confirmed by {self.who(view.decision)}, {fmt.day(view.decision.written_at)}"

    def confirmed(self, record_id: str | None) -> str:
        r = self.by_id.get(record_id or "")
        if r is None:
            return ""
        if r.author == Author.USER:
            return f"Entered by {self.who(r)}, {fmt.day(r.written_at)}"
        c = self.state.decided_by(r.id)
        if c is None:
            return ""
        return f"Confirmed by {self.who(c)}, {fmt.day(c.written_at)}"

    # 1. Summary

    def summary(self) -> Section:
        g, b = self.inp.grant, self.inp.budget
        blocks: list[Block] = [
            Table(
                ("", ""),
                (
                    ("Award number", g.award_number or ""),
                    ("Project title", g.title or ""),
                    ("Funder", fmt.FUNDER_NAMES.get(g.funder, g.funder)),
                ),
                (0.25, 0.75),
            ),
            Heading("Confirmed terms", 3),
            # The one line that says what's in force; it comes from the checks.
            Para(f"End date in force: {fmt.day(self.inp.end_date) or 'none confirmed'}."),
            Para(
                "Every confirmed term that counts, an amendment and the earlier terms it "
                "changes included. The checks decide which one is in force.",
                "small",
            ),
        ]
        terms: list[tuple[str, str, str]] = []
        for view in self.inp.terms:
            r = view.record
            if view.state != TermState.COUNTS or isinstance(r.data, BudgetLine):
                continue  # budget lines are under Spending
            label = KIND_LABELS[r.kind]
            what = self.describe(r).removeprefix(f"{label}: ")
            terms.append((label, what, self.term_confirmed(view)))
        if terms:
            blocks.append(Table(("Term", "Says", "Confirmed"), tuple(terms), (0.22, 0.5, 0.28)))

        blocks.append(Heading("Spending", 3))
        if b is not None and b.limit_cents is not None:
            over = (
                " Spending is over the award's limit."
                if any(
                    p.check == BUDGET and p.problem == OVER_LIMIT
                    for gs in self.inp.checks.grants
                    if gs.grant_id == self.inp.grant.id
                    for p in gs.problems
                )
                else ""
            )
            blocks.append(
                Para(
                    f"Spending against the award's limit: {fmt.money(b.spent_cents)} "
                    f"of {fmt.money(b.limit_cents)}.{over}"
                )
            )
        # An overspent line is a grant note from the checks, naming the lines it's about.
        budget_notes = [
            n
            for n in self.inp.checks.notes
            if n.check == BUDGET and n.grant_id == self.inp.grant.id
        ]
        overspent = {rid for n in budget_notes for rid in n.record_ids}
        views = {v.record.id: v for v in self.inp.terms}
        rows: list[tuple[str, ...]] = []
        for line in b.lines if b is not None else ():
            r = line.line
            name = r.data.name.value if isinstance(r.data, BudgetLine) else r.id
            view = views.get(r.id)
            rows.append(
                (
                    name,
                    fmt.money(line.amount_cents),
                    fmt.money(line.spent_cents),
                    "Yes" if r.id in overspent else "No",
                    self.term_confirmed(view) if view else self.confirmed(r.id),
                )
            )
        if rows:
            blocks.append(
                Table(
                    ("Budget line", "Amount", "Spent", "Over budget", "Confirmed"),
                    tuple(rows),
                    (0.3, 0.15, 0.15, 0.12, 0.28),
                )
            )
        # The checks judge spending by budget category; their own words say how.
        blocks += [Para(f"Budget note: {n.text}", "small") for n in budget_notes]
        if (b is None or b.limit_cents is None) and not rows:
            blocks.append(
                Para("No charges." if not self.inp.charges else "No confirmed limit or budget.")
            )

        blocks.append(Heading("Charges by status", 3))
        counts: Counter[str] = Counter()
        for c in self.inp.charges:
            if self.status[c.id].reversed:
                counts["reversed"] += 1
            elif self.status[c.id].accepted:
                counts["accepted"] += 1
            else:
                counts[self.status[c.id].bucket] += 1
        count_rows = [(fmt.bucket(b), str(counts[b])) for b in Bucket]
        count_rows += [
            ("Accepted", str(counts["accepted"])),
            ("Reversed", str(counts["reversed"])),
            ("All charges", str(len(self.inp.charges))),
        ]
        blocks.append(Table(("Status", "Number"), tuple(count_rows), (0.4, 0.6)))
        ready = sum(1 for s in self.inp.checks.charges if ready_for_closeout(s))
        blocks.append(
            Para(
                f"Ready for closeout: {ready} of {len(self.inp.charges)} charges "
                "(Evidence complete, accepted or fully reversed). Accepted and reversed "
                "charges are counted on their own, not in a bucket."
            )
        )
        total = sum(c.amount_cents for c in self.inp.charges)
        latest = max((c.posting_date for c in self.inp.charges), default=None)
        lines = len(self.inp.charges)
        blocks.append(
            Para(
                f"Ledger total held by FundTrail: {fmt.money(total)} across {lines} ledger "
                f"line{'s' if lines != 1 else ''}"
                + (f", latest posting date {fmt.day(latest)}" if latest else "")
                + ". Match these against the university's ledger report."
            )
        )
        return Section(SECTION_TITLES[0], blocks)

    # 2. Open at sign-off

    def snooze_of(
        self,
        charge_id: str | None = None,
        record_id: str | None = None,
        file_id: str | None = None,
    ) -> Snooze | None:
        """The current snooze on a charge, a record, a file, or (none given) the grant."""
        found = [
            r.data
            for r in self.current
            if isinstance(r.data, Snooze)
            and (r.data.charge_id, r.data.record_id, r.data.file_id)
            == (charge_id, record_id, file_id)
        ]
        return found[-1] if found else None

    def snooze_mark(self, snoozed: bool, **subject: str | None) -> str:
        if not snoozed:
            return ""
        snooze = self.snooze_of(**subject)
        if snooze is None:
            return "Snoozed"
        return f"Snoozed until {fmt.day(snooze.until)}. Note: {snooze.note}"

    @staticmethod
    def reason_marks(r: Reason) -> str:
        return "Accepted" if r.accepted_by else ""

    def open_items(self) -> Section:
        blocks: list[Block] = []
        open_charges = [c for c, _ in self.order if not ready_for_closeout(self.status[c.id])]
        if open_charges:
            blocks.append(Heading("Charges not ready for closeout", 3))
        for c in open_charges:
            s = self.status[c.id]
            blocks.append(
                Para(
                    f"{c.ledger_line_id} · {c.description} · {fmt.money(c.amount_cents)} · "
                    f"{fmt.bucket(s.bucket)}",
                    "label",
                )
            )
            if s.snoozed:
                blocks.append(Para(self.snooze_mark(True, charge_id=c.id), "small"))
            rows = tuple(
                (
                    r.check,
                    fmt.bucket(r.bucket),
                    r.text,
                    fmt.day(r.expected_by),
                    self.reason_marks(r),
                )
                for r in s.reasons
                if r.bucket != Bucket.EVIDENCE_COMPLETE
            )
            if rows:
                blocks.append(
                    Table(
                        ("Code check", "Result", "Reason", "Expected by", "Marks"),
                        rows,
                        (0.2, 0.15, 0.39, 0.13, 0.13),
                    )
                )

        problems: list[tuple[str, ...]] = []
        for g in self.inp.checks.grants:
            if g.grant_id == self.inp.grant.id and not g.accepted:
                problems += [
                    ("The grant", p.check, p.text, self.snooze_mark(g.snoozed)) for p in g.problems
                ]
        for rs in self.inp.checks.records:
            if rs.grant_id != self.inp.grant.id or rs.accepted:
                continue
            about = (
                self.file_name(rs.file_id)
                if rs.file_id
                else self.describe(self.by_id.get(rs.record_id or ""))
            )
            problems += [
                (
                    about,
                    p.check,
                    p.text,
                    self.snooze_mark(rs.snoozed, record_id=rs.record_id, file_id=rs.file_id),
                )
                for p in rs.problems
            ]
        if problems:
            blocks.append(Heading("Problems on the grant, its records and files", 3))
            blocks.append(
                Table(
                    ("About", "Check", "Problem", "Marks"),
                    tuple(problems),
                    (0.28, 0.2, 0.4, 0.12),
                )
            )

        if self.inp.held_mail:
            blocks.append(Heading("Held mail", 3))
            blocks.append(
                Table(
                    ("Sender", "Held", "Why", "Subject"),
                    tuple(
                        (
                            m.sender or "No sender address",
                            fmt.day(m.held_at),
                            HOLD_REASONS.get(m.reason, m.reason),
                            m.subject or "",
                        )
                        for m in sorted(self.inp.held_mail, key=lambda m: (m.held_at, m.id))
                    ),
                    (0.3, 0.14, 0.18, 0.38),
                )
            )

        if not blocks:
            blocks.append(
                Para(
                    (
                        "Nothing is open: there are no charges"
                        if not self.inp.charges
                        else "Nothing is open: every charge is ready for closeout"
                    )
                    + ", and there are no open problems on the grant, its records or files, "
                    "and no held mail."
                )
            )
        return Section(SECTION_TITLES[1], blocks)

    # 3. Decisions

    def subject(self, charge_id: str | None, record_id: str | None, file_id: str | None) -> str:
        if charge_id:
            return self.line_of(charge_id)
        if record_id:
            return self.describe(self.by_id.get(record_id))
        if file_id:
            return self.file_name(file_id)
        return "The grant"

    def quoted(self, cs: Iterable[Citation]) -> str:
        return " ".join(
            f"Quote: “{c.passage}” ({self.place(c)})." for c in cs if c.passage is not None
        )

    def earlier_answer(self, r: Record) -> Record | None:
        assert isinstance(r.data, Judgment)
        if r.replaces_id is not None:
            old = self.by_id.get(r.replaces_id)
            return old if old and isinstance(old.data, Judgment) else None
        # The contract's own grouping of answers to the same question; flags aren't grouped.
        ids = self.state.answers_of(r.data)
        if r.id not in ids:
            return None
        before = [i for i in ids[: ids.index(r.id)] if self.state.is_effective(i)]
        return self.by_id[before[-1]] if before else None

    @staticmethod
    def value_text(v: object) -> str:
        if isinstance(v, CitedMoney):
            return fmt.money(v.value)
        if isinstance(v, CitedDate):
            return fmt.day(v.value)
        if isinstance(v, Period):
            return f"{fmt.day(v.start)} to {fmt.day(v.end)}"
        value = getattr(v, "value", v)
        return str(value)

    def typed_values(self, r: Record, old: Record) -> str:
        new_values = {p: v for p, v in cited_values(r.data)}
        old_values = {p: v for p, v in cited_values(old.data)}
        changes: list[str] = []
        for path, v in new_values.items():
            before = old_values.get(path)
            if before is None or before.value != v.value:
                was = f" (was {self.value_text(before)})" if before is not None else ""
                changes.append(f"{path}: {self.value_text(v)}{was}")
        for path, before in old_values.items():
            if path not in new_values:
                changes.append(f"{path}: removed (was {self.value_text(before)})")
        return "; ".join(changes)

    def decisions(self) -> Section:
        rows: list[tuple[Record, str, str, str]] = []  # (stamp, decision, about, detail)
        covered: dict[str, set[str]] = {}
        for s in self.inp.checks.charges:
            for reason in s.reasons:
                if reason.accepted_by:
                    covered.setdefault(reason.accepted_by, set()).add(s.charge_id)

        for r in self.current:
            d = r.data
            if isinstance(d, AcceptedReason):
                kind = "Reusable note" if d.reusable else "One-off note"
                detail = f"{d.reason.check} ({d.reason.problem}). {kind}: {d.note}"
                if d.reuses_id:
                    earlier = self.by_id.get(d.reuses_id)
                    if earlier:
                        detail += f" Reuses the note accepted {fmt.day(earlier.written_at)}."
                lines = sorted(self.line_of(cid) for cid in covered.get(r.id, ()))
                if d.reusable and lines:
                    detail += f" Covers {', '.join(lines)}."
                rows.append(
                    (
                        r,
                        "Accepted reason",
                        self.subject(d.charge_id, d.record_id, d.file_id),
                        detail,
                    )
                )
            elif isinstance(d, Dispute) and self.state.decision(r.id) == Decision.CONFIRMED:
                detail = f"Check {d.check} disputed. Agent's reasoning: {d.reasoning} " + (
                    self.quoted(d.quotes)
                )
                rows.append(
                    (self.decision_stamp(r), "Accepted dispute", self.line_of(d.charge_id), detail)
                )
            elif isinstance(d, ChecklistRemoval):
                if d.item_record_id:
                    item = self.by_id.get(d.item_record_id)
                    needed = (
                        item.data.needed
                        if item and isinstance(item.data, ChecklistItem)
                        else d.item_record_id
                    )
                else:
                    needed = d.default_item or ""
                detail = f"Removed “{needed}”." + (f" {_sentence(d.reason)}" if d.reason else "")
                rows.append(
                    (
                        self.decision_stamp(r),
                        "Removed checklist item",
                        self.line_of(d.charge_id),
                        detail,
                    )
                )
            elif isinstance(d, Duplicate):
                detail = (
                    f"{self.file_name(d.copy_file_id)} is a copy of "
                    f"{self.file_name(d.original_file_id)}."
                ) + (f" {_sentence(d.reason)}" if d.reason else "")
                rows.append(
                    (
                        self.decision_stamp(r),
                        "Confirmed duplicate",
                        self.file_name(d.copy_file_id),
                        detail,
                    )
                )
            elif isinstance(d, Judgment) and r.author == Author.USER:
                detail = f"{d.text} Answer: {ANSWER_LABELS[d.answer]}. {d.reasoning}"
                earlier = self.earlier_answer(r)
                if earlier is not None and isinstance(earlier.data, Judgment):
                    e = earlier.data
                    detail += (
                        f" Earlier answer ({self.who(earlier)}, {fmt.day(earlier.written_at)}): "
                        f"{ANSWER_LABELS[e.answer]}. {e.reasoning}"
                    )
                about = self.subject(d.charge_id, d.record_id, d.file_id)
                rows.append((r, "Accountant's answer", about, detail))
            elif (
                r.author == Author.USER
                and d.kind in TERM_KINDS | FACT_KINDS
                and r.replaces_id is not None
            ):
                old = self.by_id.get(r.replaces_id)
                if old is not None and old.kind == r.kind:
                    rows.append((r, "Value typed", self.describe(old), self.typed_values(r, old)))

        rows.sort(key=lambda row: (row[0].written_at, row[0].id))
        blocks: list[Block] = []
        if rows:
            blocks.append(
                Table(
                    ("When", "Who", "Decision", "About", "Detail"),
                    tuple(
                        (fmt.day(stamp.written_at), self.who(stamp), what, about, detail)
                        for stamp, what, about, detail in rows
                    ),
                    (0.12, 0.13, 0.15, 0.17, 0.43),
                )
            )
        else:
            blocks.append(Para("The accountant made no decisions of these kinds."))
        blocks.append(
            Para(
                "Listed: accepted reasons with their notes, accepted disputes, removed "
                "checklist items, confirmed duplicates, answers the accountant gave over the "
                "agent's, and values the accountant typed. Term confirmations are in the "
                "summary. Thread messages, rejected suggestions and snoozes are not listed.",
                "small",
            )
        )
        return Section(SECTION_TITLES[2], blocks)

    # 4. Every charge

    def charge_rows(self) -> Section:
        rows: list[tuple[str, ...]] = []
        sub: set[int] = set()
        for i, (c, is_correction) in enumerate(self.order):
            s = self.status[c.id]
            net = self.net(c)
            if is_correction:
                sub.add(i)
            amount = fmt.money(c.amount_cents)
            if net != c.amount_cents or s.corrections:
                amount += f"\nNet {fmt.money(net)}"
            marks = self.marks(c)
            line = c.ledger_line_id + (" (correction)" if is_correction else "")
            rows.append(
                (
                    f"{line}\n{fmt.day(c.transaction_date)}",
                    c.description + (f"\n{c.vendor}" if c.vendor else ""),
                    amount,
                    fmt.bucket(s.bucket) + (f"\n{marks}" if marks else ""),
                    self.budget_line(c.id)[0],
                    self.headline_reason(s),
                )
            )
        if not rows:
            return Section(SECTION_TITLES[3], [Para("No charges.")])
        return Section(
            SECTION_TITLES[3],
            [
                Table(
                    (
                        "Line, date",
                        "Description, vendor",
                        "Amount",
                        "Bucket",
                        "Budget line",
                        "Reason",
                    ),
                    tuple(rows),
                    (0.13, 0.22, 0.12, 0.14, 0.14, 0.25),
                    sub_rows=frozenset(sub),
                )
            ],
        )

    # 5. Each charge in full

    def history_rows(self, charge_id: str) -> tuple[tuple[str, ...], ...]:
        entries: list[StatusEntry] = sorted(
            (
                e
                for e in self.inp.history
                if isinstance(e.status, ChargeStatus) and e.status.charge_id == charge_id
            ),
            key=lambda e: e.changed_at,
        )
        rows: list[tuple[str, ...]] = []
        last: Bucket | None = None
        for e in entries:
            assert isinstance(e.status, ChargeStatus)
            if e.status.bucket == last:
                continue
            last = e.status.bucket
            rows.append(
                (
                    fmt.day(e.changed_at),
                    fmt.bucket(e.status.bucket),
                    self.history_text(e),
                )
            )
        return tuple(rows)

    def charge_section(self, c: Charge, is_correction: bool) -> list[Block]:
        s = self.status[c.id]
        net = self.net(c)
        line_name, line_reason = self.budget_line(c.id)
        title = f"{c.ledger_line_id} · {c.description}"
        if is_correction:
            title += " (correction)"
        facts = [
            f"Cost date {fmt.day(c.transaction_date)}, posted {fmt.day(c.posting_date)}.",
            f"Amount {fmt.money(c.amount_cents)}"
            + (f", net {fmt.money(net)}." if net != c.amount_cents or s.corrections else "."),
            f"Account {c.account}.",
        ]
        if c.vendor:
            facts.append(_sentence(f"Vendor {c.vendor}"))
        if c.reference:
            facts.append(_sentence(f"Reference {c.reference}"))
        if c.original_line_id:
            facts.append(f"Names line {c.original_line_id} as the line it corrects.")
        marks = self.marks(c)
        facts.append(f"Bucket: {fmt.bucket(s.bucket)}" + (f" ({marks})." if marks else "."))
        if line_name:
            facts.append(f"Budget line: {line_name}.")
            if line_reason:
                facts.append(_sentence(f"Why: {line_reason}"))
        blocks: list[Block] = [Heading(title, 3), Para(" ".join(facts), "small")]

        blocks.append(Para("Evidence checklist", "label"))
        if not s.checklist:
            blocks.append(Para("No checklist items.", "small"))
        for entry in s.checklist:
            details = [self.added_by(entry)]
            if entry.amount_cents is not None:
                details.append(f"amount {fmt.money(entry.amount_cents)}")
            if entry.period is not None:
                details.append(f"covering {self.value_text(entry.period)}")
            if entry.expected_by is not None:
                details.append(f"expected by {fmt.day(entry.expected_by)}")
            if entry.removal_waiting_id:
                details.append("the agent's removal waits for the accountant")
            filled = "Filled" if entry.filled else "Missing"
            blocks.append(Para(f"{entry.needed}: {filled} ({', '.join(details)})."))
            for link_id in entry.link_ids:
                blocks += self.link_blocks(link_id)

        blocks.append(Para("Checks", "label"))
        blocks.append(
            Table(
                ("Code check", "Result", "Text"),
                tuple(
                    (
                        r.check,
                        fmt.bucket(r.bucket)
                        + (f"\n{self.reason_marks(r)}" if r.accepted_by else ""),
                        r.text,
                    )
                    for r in s.reasons
                ),
                (0.22, 0.18, 0.6),
            )
        )

        answers = [
            r for r in self.current if isinstance(r.data, Judgment) and r.data.charge_id == c.id
        ]
        if answers:
            blocks.append(Para("Answers", "label"))
        for r in answers:
            assert isinstance(r.data, Judgment)
            d = r.data
            whose = "Agent's answer" if r.author == Author.AGENT else "Accountant's answer"
            blocks.append(Para(f"{whose}, {fmt.day(r.written_at)}: {d.text}"))
            blocks.append(Para(f"{ANSWER_LABELS[d.answer]}. {d.reasoning}", "small"))
            if d.rule:
                title_ = self.inp.rule_titles.get(d.rule)
                blocks.append(Para(f"Rule {d.rule}" + (f": {title_}" if title_ else ""), "small"))
            blocks += self.quotes(d.quotes)

        blocks.append(Para("Status history", "label"))
        rows = self.history_rows(c.id)
        if rows:
            blocks.append(Table(("Date", "Bucket", "What changed"), rows, (0.15, 0.2, 0.65)))
        else:
            blocks.append(Para("No status history recorded.", "small"))
        return blocks

    def link_blocks(self, link_id: str) -> list[Block]:
        link = self.by_id.get(link_id)
        if link is None or not isinstance(link.data, Link):
            return []
        d = link.data
        target = self.state.current_version(d.record_id) or self.by_id.get(d.record_id)
        text = self.describe(target)
        if d.amount_cents is not None:
            text += f", linked for {fmt.money(d.amount_cents)}"
        text += f" ({'agent' if link.author == Author.AGENT else 'accountant'}, "
        text += f"{fmt.day(link.written_at)})."
        if d.reason:
            text += f" {_sentence(d.reason)}"
        blocks: list[Block] = [Para(text, "small")]
        if d.part is not None:
            if d.part.passage is not None:
                blocks.append(Quote(d.part.passage, self.place(d.part)))
            else:
                value = self.value_at(target, d.part) if target is not None else None
                blocks.append(Para(f"Cited: {self.place(d.part, value)}", "small"))
        return blocks

    @staticmethod
    def value_at(record: Record, part: Citation) -> str | None:
        """The value the record read at the part's place, as the document writes it."""
        for _, v in cited_values(record.data):
            c = v.citation
            if c is not None and c.file_id == part.file_id and c.location == part.location:
                return v.text or str(v.value)
        return None

    def charge_sections(self) -> Section:
        blocks: list[Block] = []
        for c, is_correction in self.order:
            blocks += self.charge_section(c, is_correction)
        return Section(SECTION_TITLES[4], blocks or [Para("No charges.")])

    # 6. Sources

    def sources(self) -> Section:
        # Cited by any record that isn't rejected or replaced, a waiting term included.
        cited: set[str] = set()
        for r in self.inp.records:
            if self.state.decision(r.id) == Decision.REJECTED or self.state.is_replaced(r.id):
                continue
            cited.update(c.file_id for c in citations(r.data))
        copies = {
            r.data.copy_file_id: r.data.original_file_id
            for r in self.current
            if isinstance(r.data, Duplicate)
        }

        def order(f: EvidenceFile) -> tuple[object, ...]:
            return (f.arrived_at, f.name, f.id)

        rows: list[tuple[str, ...]] = []
        for f in sorted((f for f in self.inp.files if f.id in cited), key=order):
            name = [f.name, f.media_type]
            if f.parent_id:
                name.append(f"Attachment of {self.file_name(f.parent_id)}")
            if f.id in copies:
                name.append(f"Duplicate of {self.file_name(copies[f.id])}")
            came = [f"{fmt.SOURCE_LABELS.get(f.source, f.source)}, arrived {fmt.day(f.arrived_at)}"]
            if f.document_date:
                came.append(f"Dated {fmt.day(f.document_date)}")
            if f.sender:
                came.append(f"From {f.sender}")
            rows.append(("\n".join(name), "\n".join(came), f.sha256))
        blocks: list[Block] = [
            Para(
                "Every file a record cites, including a term still waiting to be confirmed. "
                "The SHA-256 (Secure Hash Algorithm, 256-bit) checksum shows a file is the "
                "same one later.",
                "small",
            ),
            Table(("File", "How it came", "SHA-256"), tuple(rows), (0.26, 0.2, 0.54), mono_column=2)
            if rows
            else Para("No file is cited."),
        ]
        uncited = sorted((f for f in self.inp.files if f.id not in cited), key=order)
        blocks.append(Heading("Files on the grant that no record cites", 3))
        if uncited:
            blocks.append(
                Table(
                    ("File", "How it came"),
                    tuple(
                        (
                            f.name,
                            f"{fmt.SOURCE_LABELS.get(f.source, f.source)}, arrived "
                            f"{fmt.day(f.arrived_at)}",
                        )
                        for f in uncited
                    ),
                    (0.5, 0.5),
                )
            )
        else:
            blocks.append(Para("None.", "small"))
        return Section(SECTION_TITLES[5], blocks)

    # 7. Sign-off

    def sign_off(self) -> Section:
        so = self.inp.sign_off
        blocks: list[Block] = []
        if so is None:
            blocks.append(Para(f"Not signed. This is a draft as of {fmt.moment(self.inp.now)}."))
        else:
            # Inputs make sure the sign-off is the preparer's.
            p = self.inp.preparer
            who = f"{p.name or p.email} ({p.email})"
            blocks.append(Para(f"Signed off by {who} on {fmt.moment(so.signed_at)}."))
            blocks.append(Para("Note for the reviewer", "label"))
            blocks.append(Para(so.note or "No note."))
        blocks.append(SignLines("Reviewed by", ("Name", "Title", "Signature", "Date")))
        return Section(SECTION_TITLES[6], blocks)


def report_view(inp: ReportInputs) -> ReportView:
    rep = _Report(inp)
    return ReportView(
        award_number=inp.grant.award_number or "",
        project_title=inp.grant.title or "",
        as_of=fmt.moment(inp.now),
        signed=inp.sign_off is not None,
        sections=[
            rep.summary(),
            rep.open_items(),
            rep.decisions(),
            rep.charge_rows(),
            rep.charge_sections(),
            rep.sources(),
            rep.sign_off(),
        ],
    )
