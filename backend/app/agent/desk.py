"""The agent's desk: what code hands the model at the start of a run.

Every run gets a header (award number, the clock's "now", the end date in force, each term and
its state), the open questions waiting for the agent, and the two lists, one line per charge and
one per document, built from the saved facts. What the trigger brings comes in full (section 3 of
the proposal). On a small grant the lists go in the first message; on a large one the message holds
the counts and the agent pages and searches with the tools. Code hides nothing: every tool works on
the whole grant.
"""

from collections.abc import Sequence
from typing import Any

from .adapter import (
    FACT_KINDS,
    TERM_KINDS,
    TRIGGER_CHARGE,
    TRIGGER_CLOCK,
    TRIGGER_FILE,
    TRIGGER_RECORD,
    TRIGGER_THREAD,
    Author,
    Bill,
    Charge,
    Decision,
    EvidenceFile,
    Link,
    PeriodOfPerformance,
    Record,
    RecordState,
    agent_questions,
    cited_values,
)
from .adapter import (
    Judgment as JudgmentData,
)
from .context import RunContext
from .files import CantOpen, open_file

# Above this many charges or documents, the lists go through the tools instead of the first message.
FULL_LIST_LIMIT = 300


def money(cents: int | None) -> str:
    if cents is None:
        return "?"
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) / 100:,.2f}"


def _value(v: Any) -> str:
    return str(v.value) if hasattr(v, "value") else str(v)


def record_summary(r: Record) -> str:
    """One line: the record's kind and its values."""
    parts = [f"{r.id} {r.kind}"]
    data = r.data
    for path, v in cited_values(data):
        val = (
            money(v.value)
            if isinstance(v.value, int) and not isinstance(v.value, bool)
            else _value(v)
        )
        parts.append(f"{path}={val}")
    for name in (
        "category",
        "label",
        "record_id",
        "charge_id",
        "amount_cents",
        "question",
        "answer",
        "rule",
    ):
        if hasattr(data, name) and getattr(data, name) is not None:
            val = getattr(data, name)
            parts.append(f"{name}={money(val) if name == 'amount_cents' else val}")
    if r.replaces_id:
        parts.append(f"replaces {r.replaces_id}")
    return " ".join(parts)


def record_state(state: RecordState, r: Record) -> str:
    if state.decision(r.id) == Decision.REJECTED:
        return "rejected"
    if state.is_waiting(r.id):
        return "waiting for the accountant"
    if state.is_current(r.id):
        if r.kind in TERM_KINDS:
            return (
                "confirmed"
                if (r.author == Author.USER or state.decision(r.id) == Decision.CONFIRMED)
                else "unconfirmed"
            )
        return "current"
    return "replaced"


def confirmed_terms(state: RecordState) -> list[Record]:
    return [
        r
        for r in state.current()
        if r.kind in TERM_KINDS
        and (r.author == Author.USER or state.decision(r.id) == Decision.CONFIRMED)
    ]


def end_date_in_force(state: RecordState) -> str:
    periods = [r.data for r in confirmed_terms(state) if isinstance(r.data, PeriodOfPerformance)]
    if not periods:
        return "none confirmed yet"
    latest = max(periods, key=lambda p: p.dated.value)
    return str(latest.end.value)


def files_of(r: Record) -> set[str]:
    return {v.citation.file_id for _, v in cited_values(r.data) if v.citation is not None}


def charge_line(ctx: RunContext, c: Charge) -> str:
    state = ctx.state()
    status = next((s for s in ctx.checks().charges if s.charge_id == c.id), None)
    links = [r for r in state.current() if isinstance(r.data, Link) and r.data.charge_id == c.id]
    parts = [
        c.id,
        c.ledger_line_id,
        f"cost {c.transaction_date}",
        f"posted {c.posting_date}",
        money(c.amount_cents),
        c.vendor or "no vendor",
        c.account,
        f"ref {c.reference}" if c.reference else "no ref",
        c.description,
    ]
    if c.original_line_id:
        parts.append(f"corrects {c.original_line_id}")
    if status is not None:
        parts.append(f"bucket {status.bucket}")
        missing = [e.needed for e in status.checklist if not e.filled]
        if missing:
            parts.append("missing: " + "; ".join(missing))
    if links:
        parts.append("links: " + ", ".join(f"{r.id} to {r.record_id}" for r in links))
    return " | ".join(parts)


def document_line(ctx: RunContext, f: EvidenceFile) -> str:
    state = ctx.state()
    facts = [
        r for r in state.current() if r.kind in FACT_KINDS | TERM_KINDS and f.id in files_of(r)
    ]
    parts = [f.id, f.name, f.source, f"arrived {f.arrived_at:%Y-%m-%d}"]
    if f.sender:
        parts.append(f"from {f.sender}")
    if facts:
        parts.append("facts: " + "; ".join(record_summary(r) for r in facts))
        for bill in facts:
            if not isinstance(bill.data, Bill):
                continue
            linked = sum(
                r.data.amount_cents or 0
                for r in state.current()
                if isinstance(r.data, Link) and r.data.record_id == bill.id
            )
            total = bill.data.total.value
            parts.append(f"{bill.id} linked {money(linked)}, unlinked {money(total - linked)}")
    else:
        parts.append("no facts read yet")
    return " | ".join(parts)


def charge_lines(ctx: RunContext, offset: int = 0, limit: int = FULL_LIST_LIMIT) -> list[str]:
    return [charge_line(ctx, c) for c in list(ctx.inputs.charges)[offset : offset + limit]]


def document_lines(ctx: RunContext, offset: int = 0, limit: int = FULL_LIST_LIMIT) -> list[str]:
    return [document_line(ctx, f) for f in list(ctx.inputs.files)[offset : offset + limit]]


def charge_in_full(ctx: RunContext, c: Charge) -> str:
    """One charge in full: checklist, failing checks, records about it, and its thread."""
    state = ctx.state()
    status = next((s for s in ctx.checks().charges if s.charge_id == c.id), None)
    out = [charge_line(ctx, c)]
    if status is not None:
        out.append("Checklist:")
        for e in status.checklist:
            item = e.default_item and f"default {e.default_item}" or f"item {e.item_record_id}"
            extra = f", amount {money(e.amount_cents)}" if e.amount_cents is not None else ""
            due = f", expected by {e.expected_by}" if e.expected_by else ""
            out.append(f"- {item}: {e.needed}{extra}{due}: {'filled' if e.filled else 'missing'}")
        failing = [r for r in status.reasons if r.bucket != "evidence_complete"]
        out.append("Checks failing:" if failing else "Checks failing: none")
        out += [f"- {r.check} ({r.problem}): {r.bucket}: {r.text}" for r in failing]
    about = [r for r in state.records if r.charge_id == c.id]
    out.append("Records about this charge, in order:")
    out += [f"- {record_summary(r)} [{r.author}, {record_state(state, r)}]" for r in about] or [
        "- none"
    ]
    thread = [m for m in ctx.inputs.thread_messages if m.charge_id == c.id]
    if thread:
        out.append("Thread:")
        out += [f"- {m.written_at:%Y-%m-%d %H:%M} {m.author}: {m.text}" for m in thread]
    if c.original_line_id:
        original = next(
            (o for o in ctx.inputs.charges if o.ledger_line_id == c.original_line_id), None
        )
        out.append(
            f"The line it corrects: {charge_line(ctx, original)}"
            if original
            else "The line it corrects isn't on file."
        )
    return "\n".join(out)


def record_in_full(ctx: RunContext, r: Record) -> str:
    state = ctx.state()
    replaced_by = [x.id for x in state.records if x.replaces_id == r.id]
    lines = [
        f"{record_summary(r)} [{r.author}, {record_state(state, r)}, "
        f"written {r.written_at:%Y-%m-%d}]",
        r.data.model_dump_json(exclude_none=True),
    ]
    if r.replaces_id:
        lines.append(f"It replaces {r.replaces_id}.")
    if replaced_by:
        lines.append("Replaced by: " + ", ".join(replaced_by))
    return "\n".join(lines)


def header(ctx: RunContext) -> str:
    i = ctx.inputs
    state = ctx.state()
    g = i.grant
    terms = [
        r for r in state.records if r.kind in TERM_KINDS and record_state(state, r) != "replaced"
    ]
    lines = [
        f"Grant {g.id}: award {g.award_number or 'not read yet'}, "
        f"{g.title or 'title not read yet'}, funder {g.funder}.",
        f"Now: {i.now:%Y-%m-%d %H:%M} UTC. End date in force: {end_date_in_force(state)}.",
        "Terms:" if terms else "Terms: none yet.",
    ]
    lines += [f"- {record_summary(r)} [{record_state(state, r)}]" for r in terms]
    questions = agent_questions(ctx.checks())
    lines.append(
        "Open questions waiting for you:" if questions else "Open questions waiting for you: none."
    )
    lines += [
        f"- {q.question} on charge {q.charge_id}" + (f" about {q.record_id}" if q.record_id else "")
        for q in questions
    ]
    return "\n".join(lines)


def lists(ctx: RunContext) -> str:
    i = ctx.inputs
    if len(i.charges) > FULL_LIST_LIMIT or len(i.files) > FULL_LIST_LIMIT:
        return (
            f"The grant has {len(i.charges)} charges and {len(i.files)} documents: too many "
            "to list here. Use list_charges, list_documents and search to look through them."
        )
    return "\n".join(
        [
            f"Charges ({len(i.charges)}):",
            *(charge_lines(ctx) or ["none"]),
            f"Documents ({len(i.files)}):",
            *(document_lines(ctx) or ["none"]),
        ]
    )


def missing_items(ctx: RunContext, only: Sequence[str] = ()) -> list[str]:
    out: list[str] = []
    by_id = {c.id: c for c in ctx.inputs.charges}
    for status in ctx.checks().charges:
        if only and status.charge_id not in only:
            continue
        c = by_id.get(status.charge_id)
        if c is None:
            continue
        for e in status.checklist:
            if e.filled:
                continue
            item = f"default {e.default_item}" if e.default_item else f"item {e.item_record_id}"
            amount = f", amount {money(e.amount_cents)}" if e.amount_cents is not None else ""
            period = f", period {e.period.start} to {e.period.end}" if e.period else ""
            due = f", expected by {e.expected_by}" if e.expected_by else ""
            out.append(
                f"- charge {c.id} ({c.ledger_line_id}, {money(c.amount_cents)}, "
                f"{c.vendor or 'no vendor'}): "
                f"{item}: {e.needed}{amount}{period}{due}"
            )
    return out


def trigger_section(ctx: RunContext) -> list[dict[str, Any]]:
    """The content blocks for what started the run, in full."""
    i = ctx.inputs
    t = i.trigger
    state = ctx.state()
    blocks: list[dict[str, Any]] = []
    if t.kind == TRIGGER_FILE:
        f = next(x for x in i.files if x.id == t.id)
        text = [
            f"What arrived: file {f.id}. Read it fully, once, and record every value a check or a "
            "later match could need.",
            AWARD_NOTICE_GUIDANCE,
            "Checklist items still missing on the grant. Which of these does this file fill?",
            *(missing_items(ctx) or ["- none"]),
        ]
        blocks.append({"type": "text", "text": "\n".join(text)})
        try:
            opened = open_file(f, i.read_file(f))
        except CantOpen as error:
            blocks.append({"type": "text", "text": f"The file couldn't be sent: {error}."})
        else:
            if opened.document is not None:
                ctx.documents.append(opened.document)
            if opened.image is not None:
                ctx.images[f.id] = opened.image
            blocks += opened.blocks
            if f.parent_id or any(x.parent_id == f.id for x in i.files):
                related = [x for x in i.files if x.id == f.parent_id or x.parent_id == f.id]
                blocks.append(
                    {
                        "type": "text",
                        "text": "Related files: "
                        + "; ".join(document_line(ctx, x) for x in related),
                    }
                )
    elif t.kind == TRIGGER_CHARGE:
        ids = list(i.charge_ids) or [t.id or ""]
        charges = [c for c in i.charges if c.id in ids]
        text = [f"What arrived: {len(charges)} charge(s). Match each to the evidence on file."]
        text += [charge_in_full(ctx, c) for c in charges]
        blocks.append({"type": "text", "text": "\n\n".join(text)})
    elif t.kind == TRIGGER_RECORD:
        r = state.by_id.get(t.id or "")
        text = ["What happened: the accountant wrote a record that leaves a question open for you."]
        if r is not None:
            text.append(record_in_full(ctx, r))
        affected = {q.charge_id for q in agent_questions(ctx.checks())}
        text += [charge_in_full(ctx, c) for c in i.charges if c.id in affected]
        blocks.append({"type": "text", "text": "\n\n".join(text)})
    elif t.kind == TRIGGER_THREAD:
        message = next((m for m in i.thread_messages if m.id == t.id), None)
        text = ["What happened: the accountant wrote in a thread. Reply with post_message."]
        if message is not None:
            subject = [
                m
                for m in i.thread_messages
                if (m.charge_id, m.record_id) == (message.charge_id, message.record_id)
            ]
            text.append("The thread:")
            text += [f"- {m.written_at:%Y-%m-%d %H:%M} {m.author}: {m.text}" for m in subject]
            if message.charge_id:
                c = next((x for x in i.charges if x.id == message.charge_id), None)
                if c is not None:
                    text.append(charge_in_full(ctx, c))
            elif message.record_id and message.record_id in state.by_id:
                text.append(record_in_full(ctx, state.by_id[message.record_id]))
        text.append(
            "An instruction to change something comes back from you as a suggestion: write "
            "the record, and it waits for the accountant."
        )
        blocks.append({"type": "text", "text": "\n".join(text)})
    elif t.kind == TRIGGER_CLOCK:
        # A closeout review can run in batches of charges, each its own run (charge_ids).
        only = list(i.charge_ids)
        links = [
            r
            for r in state.current()
            if isinstance(r.data, Link) and (not only or r.data.charge_id in only)
        ]
        unlinked = [
            document_line(ctx, f) for f in i.files if "unlinked $0.00" not in document_line(ctx, f)
        ]
        text = [
            "What happened: the closeout window opened. Review every link on the grant, and every "
            "checklist item still missing. Suggest a fix, with its reason, for any link that "
            "looks wrong.",
            "Every link:",
            *([f"- {record_summary(r)}" for r in links] or ["- none"]),
            "Every missing item:",
            *(missing_items(ctx, only) or ["- none"]),
            "Documents with money nobody charged, or no facts:",
            *(unlinked or ["- none"]),
        ]
        blocks.append({"type": "text", "text": "\n".join(text)})
    return blocks


def first_message(ctx: RunContext) -> list[dict[str, Any]]:
    return [
        {"type": "text", "text": header(ctx)},
        {"type": "text", "text": lists(ctx)},
        *trigger_section(ctx),
    ]


def search_lines(ctx: RunContext, query: str) -> list[str]:
    words = [w.lower() for w in query.split() if w]
    lines = charge_lines(ctx, 0, len(ctx.inputs.charges)) + document_lines(
        ctx, 0, len(ctx.inputs.files)
    )
    return [line for line in lines if all(w in line.lower() for w in words)]


def judgments_about(state: RecordState, charge_ids: Sequence[str]) -> list[Record]:
    return [
        r
        for r in state.current()
        if isinstance(r.data, JudgmentData) and r.data.charge_id in charge_ids
    ]


AWARD_NOTICE_GUIDANCE = (
    "If this is an award notice, an amendment or a program solicitation: read its free-text "
    "conditions as well as its labeled fields, and write each condition as a term "
    "(an approval_rule when it says who must approve what, otherwise an other_term). Every award "
    "notice gets exactly one notice term: its amendment number, its amendment type, and the "
    "amounts it prints for Amount Obligated by this Amendment (obligated_by_amendment) and Total "
    "Amount Obligated to Date (obligated_to_date), because code checks each notice's running "
    "total against the one before. Write each budget line and sub-line it prints as its own "
    "budget_line, with its NSF category from the fixed list. Totals such as Total Direct Costs "
    "are sums, not terms."
)
