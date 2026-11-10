"""Mail held from unknown senders, and letting it in (decision 0025).

A held message stays held while `rules.still_held` says so. Once it isn't, because the
accountant let it in or the sender became known, its files arrive at that moment, as
evidence files, with the attachments it skipped. A dismissed message stays stored and
never arrives.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.contracts.evidence import EvidenceFile, Source, storage_path
from app.contracts.mail import HeldMail
from app.contracts.records import MailAction, MailDecision, Person
from app.contracts.rules import RecordState, still_held
from app.contracts.workspaces import Grant
from app.ingest.incoming import let_in_skips

from . import store
from .platform import Platform
from .store import Conn


def known_senders(conn: Conn, grant: Grant, state: RecordState) -> set[str]:
    """The grant's known senders, lower case: the people its terms that count name with an
    address (the award letter's, confirmed, and those the accountant added), and the
    accountant's own sign-in address."""
    found = {
        r.data.email.value.strip().lower()
        for r in state.current()
        if isinstance(r.data, Person) and r.data.email is not None
    }
    owner = store.get_user(conn, store.workspace_by_id(conn, grant.workspace_id).owner_id)
    if owner is not None:
        found.add(owner.email.strip().lower())
    return found


def grant_held_mail(conn: Conn, grant: Grant, now: datetime) -> list[HeldMail]:
    return [
        h for h in store.list_held_mail(conn, grant.workspace_id, now) if h.grant_id == grant.id
    ]


def still_held_mail(conn: Conn, grant: Grant, now: datetime, state: RecordState) -> list[HeldMail]:
    """The grant's messages still held at `now`: the problem list's rows and the report's."""
    known = known_senders(conn, grant, state)
    return [h for h in grant_held_mail(conn, grant, now) if still_held(h, state, known)]


def _dismissed(held: HeldMail, state: RecordState) -> bool:
    return any(
        isinstance(r.data, MailDecision)
        and r.data.held_mail_id == held.id
        and r.data.action == MailAction.DISMISS
        for r in state.current()
    )


def let_in_released(p: Platform, conn: Conn, grant: Grant, now: datetime) -> list[EvidenceFile]:
    """Every held message on the grant no longer held, not dismissed, and not arrived yet
    arrives now: its files become evidence files, the message before its attachments,
    and the attachments it skipped are reported at this moment (`let_in_skips`). The
    caller holds the grant's lock, rechecks and queues the runs."""
    state = RecordState(
        store.list_records(conn, grant.id, now), store.list_files(conn, grant.id, now)
    )
    known = known_senders(conn, grant, state)
    arrived: list[EvidenceFile] = []
    for held in grant_held_mail(conn, grant, now):
        if still_held(held, state, known) or _dismissed(held, state):
            continue
        if store.has_gmail_message(conn, grant.id, held.source_ref):
            continue  # it arrived already
        parent: str | None = None
        for held_file in held.files:
            file_id = str(uuid.uuid4())
            f = EvidenceFile(
                id=file_id,
                workspace_id=grant.workspace_id,
                grant_id=grant.id,
                source=Source.GMAIL,
                name=held_file.name,
                media_type=held_file.media_type,
                storage_path=storage_path(grant.workspace_id, grant.id, file_id, held_file.name),
                sha256=held_file.sha256,
                arrived_at=now,
                sender=held.sender,
                source_ref=held.source_ref,
                parent_id=parent,
            )
            store.insert_file(conn, f)
            p.storage.put(f.storage_path, p.storage.get(held_file.storage_path), f.media_type)
            parent = parent or file_id
            arrived.append(f)
        store.insert_skipped(conn, let_in_skips(held, now))
    return arrived
