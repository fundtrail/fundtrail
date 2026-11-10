"""The evidence report (decision 0022): gathers #38's ReportInputs and builds the PDF.

The report takes the grant page's own bodies (its terms, budget figures and end date), so
the report and the screens agree. The draft route builds it with no sign-off. Signing off
builds it with the sign-off on it, under the grant's lock (`actions.add_sign_off`), stores
the PDF, and writes the sign_off record with the report's path, checksum and snapshot.
"""

from __future__ import annotations

from datetime import datetime

from app.contracts.checks import StatusEntry
from app.contracts.records import Record
from app.contracts.signoff import SignOffSnapshot
from app.contracts.workspaces import Grant, User
from app.db import store
from app.db.platform import Platform
from app.db.store import Conn
from app.packet import ReportInputs, Signing, build_report

from .views import budget, load_snapshot, snapshot_now, summary, term_views

# Files whose text the report quotes by line number.
_TEXT_TYPES = ("text/", "message/rfc822")


def report_inputs(
    p: Platform,
    conn: Conn,
    grant: Grant,
    now: datetime,
    preparer_id: str,
    signing: Signing | None,
) -> ReportInputs:
    """Everything on the grant at the workspace's "now", which `now` is: the caller reads it
    in the same transaction. The preparer is the user who signs off, or for a draft the
    user asking for it, never assumed from the workspace (issue 160)."""
    snap = load_snapshot(p, conn, grant)
    assert snap.now == now, "the report is built at the workspace's now"
    preparer = store.get_user(conn, preparer_id) or User(
        id=preparer_id, email="unknown@university.example"
    )
    texts: dict[str, str] = {}
    for f in snap.files:
        if f.media_type.startswith(_TEXT_TYPES):
            texts[f.id] = p.storage.get(f.storage_path).decode("utf-8", errors="replace")
    history = tuple(
        StatusEntry(changed_at=row.changed_at, trigger=row.trigger, status=row.status)
        for row in store.grant_status_history(conn, grant.id, now)
    )
    records: tuple[Record, ...] = tuple(snap.records)
    return ReportInputs(
        grant=grant,
        now=now,
        preparer=preparer,
        charges=tuple(snap.charges),
        files=tuple(snap.files),
        records=records,
        checks=snap.output,
        history=history,
        terms=tuple(term_views(snap)),
        budget=budget(snap),
        end_date=summary(snap).end_date,
        # Held mail has no table until #43; once it does, only the messages for which
        # rules.still_held is true go here.
        held_mail=(),
        thread_messages=tuple(snap.messages),
        sign_off=signing,
        file_texts=texts,
    )


def draft_report(p: Platform, conn: Conn, grant: Grant, now: datetime, user_id: str) -> bytes:
    """The current draft: the report as this user would sign it now, with no sign-off on it."""
    return build_report(report_inputs(p, conn, grant, now, user_id, None))


def signed_report_maker(p: Platform, user_id: str):  # noqa: ANN201
    """What actions.add_sign_off calls under the grant's lock: the PDF with the sign-off on
    it, and the snapshot it stores (decision 0022). The user signing off is the preparer."""

    def make(
        conn: Conn, grant: Grant, now: datetime, note: str | None
    ) -> tuple[bytes, SignOffSnapshot]:
        signing = Signing(author_user_id=user_id, signed_at=now, note=note)
        pdf = build_report(report_inputs(p, conn, grant, now, user_id, signing))
        return pdf, snapshot_now(load_snapshot(p, conn, grant))

    return make
