"""Where the Gmail and Drive checker's finds are stored (decisions 0013 and 0025).

`DbSink` is the checker's `IngestSink`. The checker saves its progress only after each
check, so after a failure it brings the same message or file again. Each write here
takes the checker's progress row and the grant's row lock, checks whether it already
has what it's given, and stores it with its progress in one transaction:

- a Gmail message is already taken in when the grant has it as an evidence file or as
  held mail, by its Gmail message ID, one check for both, so a message that arrived is
  never held and a held one (dismissed, say) never comes in on its own;
- a Drive file, when the grant's progress has that Drive file ID at that version.

`check_and_save` runs one check from the saved progress and saves where it got to.
Nothing schedules it yet.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.contracts.evidence import EvidenceFile
from app.contracts.mail import CheckerProgress, DriveVersion, HeldFile, SkippedFile
from app.contracts.runs import AgentRun, Trigger, TriggerKind
from app.contracts.workspaces import Grant
from app.ingest.checker import CheckState, GrantNow, check_once
from app.ingest.incoming import (
    GrantRoute,
    IncomingFile,
    PendingHold,
    to_evidence_file,
    to_held_mail,
)
from app.ingest.sources import DriveSource, MailSource

from . import clock, jobs, store
from .pings import ping_changed, ping_run
from .platform import Platform
from .pool import transaction
from .recheck import recheck_grant
from .store import Conn


def _new_id() -> str:
    return str(uuid.uuid4())


def drive_version(f: IncomingFile) -> str:
    """The version of a Drive file, as `drive_files.version_of` gave it: the checker keys
    each Drive file `drive:{file ID}:{version}`."""
    prefix = f"drive:{f.source_ref}:"
    if f.source != "drive" or not f.key.startswith(prefix):
        raise ValueError(f"not a Drive file's key: {f.key}")
    return f.key[len(prefix) :]


def held_storage_path(held: PendingHold, held_id: str, index: int, name: str) -> str:
    """Where a held message's file is stored: under its grant, apart from evidence files,
    numbered so a message and its attachments never share a path."""
    return f"{held.workspace_id}/{held.grant_id}/held-{held_id}/{index}-{name}"


def _seen(progress: CheckerProgress, message_id: str) -> CheckerProgress:
    ids = sorted({*progress.seen_message_ids, message_id})
    return progress.model_copy(update={"seen_message_ids": tuple(ids)})


def _with_version(progress: CheckerProgress, version: DriveVersion) -> CheckerProgress:
    others = [
        v
        for v in progress.drive_versions
        if (v.grant_id, v.drive_file_id) != (version.grant_id, version.drive_file_id)
    ]
    ordered = sorted([*others, version], key=lambda v: (v.grant_id, v.drive_file_id))
    return progress.model_copy(update={"drive_versions": tuple(ordered)})


def arrive_files(
    p: Platform, conn: Conn, grant: Grant, files: Sequence[IncomingFile]
) -> list[EvidenceFile]:
    """Stores arrived files as evidence files, a message before its attachments. The
    caller holds the grant's lock and rechecks."""
    ids: dict[str, str] = {}
    stored: list[EvidenceFile] = []
    for f in files:
        file_id = _new_id()
        ids[f.key] = file_id
        parent = ids.get(f.parent_key) if f.parent_key else None
        evidence = to_evidence_file(f, file_id=file_id, parent_id=parent)
        evidence = evidence.model_copy(update={"exported_from": f.exported_from})
        store.insert_file(conn, evidence)
        # Stored after the row passed its constraints. If the commit then fails, the
        # object is left without a row; nothing reads it.
        p.storage.put(evidence.storage_path, f.data, evidence.media_type)
        stored.append(evidence)
    return stored


def queue_arrivals(
    p: Platform, conn: Conn, grant: Grant, files: Sequence[EvidenceFile]
) -> list[AgentRun]:
    """Recheck the grant at the files' arrival and queue a run for each, as an upload does."""
    if not files:
        return []
    now = max(f.arrived_at for f in files)
    triggers = {f.id: Trigger(kind=TriggerKind.FILE, id=f.id) for f in files}
    recheck_grant(conn, p.checks, grant, now, triggers[files[0].id], file_triggers=triggers)
    return [jobs.queue_run(conn, grant, triggers[f.id], f.arrived_at) for f in files]


class DbSink:
    """The checker's sink: stores what it brings, once."""

    def __init__(self, p: Platform) -> None:
        self.p = p

    def store(self, files: list[IncomingFile], skipped: Sequence[SkippedFile] = ()) -> None:
        if not files:
            for s in skipped:
                self.skip(s)
            return
        first = files[0]
        runs: list[AgentRun] = []
        with transaction(self.p.pool) as conn:
            progress = store.lock_progress(conn)
            grant = store.get_grant(conn, first.grant_id, lock=True)
            assert grant is not None
            if first.source == "gmail":
                assert first.source_ref is not None
                if store.has_message(conn, grant.id, first.source_ref):
                    return
                progress = _seen(progress, first.source_ref)
            elif first.source == "drive":
                assert first.source_ref is not None
                version = DriveVersion(
                    grant_id=grant.id, drive_file_id=first.source_ref, version=drive_version(first)
                )
                if version in progress.drive_versions:
                    return
                progress = _with_version(progress, version)
            stored = arrive_files(self.p, conn, grant, files)
            store.insert_skipped(conn, skipped)
            runs = queue_arrivals(self.p, conn, grant, stored)
            store.save_progress(conn, progress)
        for run in runs:
            ping_run(self.p.pinger, run)
        ping_changed(self.p.pinger, grant.workspace_id, grant.id, "evidence", "statuses")

    def hold(self, held: PendingHold) -> None:
        with transaction(self.p.pool) as conn:
            progress = store.lock_progress(conn)
            grant = store.get_grant(conn, held.grant_id, lock=True)
            assert grant is not None
            if store.has_message(conn, grant.id, held.gmail_message_id):
                return
            held_id = _new_id()
            stored: list[HeldFile] = []
            for index, f in enumerate(held.files):
                path = held_storage_path(held, held_id, index, f.name)
                self.p.storage.put(path, f.data, f.media_type)
                stored.append(
                    HeldFile(
                        name=f.name,
                        media_type=f.media_type,
                        storage_path=path,
                        sha256=f.sha256,
                        # Ruling 43: the sent date its evidence file takes at let-in, as
                        # the checker dated it.
                        document_date=f.document_date,
                    )
                )
            store.insert_held_mail(conn, to_held_mail(held, held_id=held_id, files=tuple(stored)))
            store.save_progress(conn, _seen(progress, held.gmail_message_id))
        ping_changed(self.p.pinger, grant.workspace_id, grant.id, "held_mail")

    def skip(self, skipped: SkippedFile) -> None:
        with transaction(self.p.pool) as conn:
            store.lock_progress(conn)
            grant = store.get_grant(conn, skipped.grant_id, lock=True)
            assert grant is not None
            store.insert_skipped(conn, [skipped])
            recheck_grant(
                conn, self.p.checks, grant, skipped.skipped_at, Trigger(kind=TriggerKind.CLOCK)
            )
        ping_changed(self.p.pinger, grant.workspace_id, grant.id, "statuses")


def check_and_save(
    p: Platform,
    *,
    mail: MailSource | None,
    drive: DriveSource | None,
    mailbox: str,
    routes: list[GrantRoute],
    now: GrantNow | None = None,
) -> None:
    """One check of Gmail and Drive from the saved progress, then saves where it got to.

    Arrivals are dated by each grant's clock (`clock.grant_clock`) unless `now` is given.
    What the sink stored during the check is in its progress already. The save keeps
    every message ID the progress holds by then, a concurrent check's included, adds this
    check's, and moves the mailbox position and the finished first searches forward: a
    check never takes back what another one saved (`merged_progress`).
    """
    with transaction(p.pool) as conn:
        start = store.lock_progress(conn)
    state = CheckState.from_progress(start)
    check_once(
        mail=mail,
        drive=drive,
        mailbox=mailbox,
        routes=routes,
        state=state,
        now=now or clock.grant_clock(p),
        sink=DbSink(p),
    )
    with transaction(p.pool) as conn:
        stored = store.lock_progress(conn)
        store.save_progress(conn, merged_progress(start, stored, state.to_progress()))


def _later_cursor(a: str | None, b: str | None) -> str | None:
    """The later of two mailbox positions. Gmail's are numeric history IDs, so the larger;
    a position that isn't a number (the disk stand-in's) is taken as given."""
    if a and b and a.isdigit() and b.isdigit():
        return a if int(a) >= int(b) else b
    return a or b


def merged_progress(
    start: CheckerProgress, stored: CheckerProgress, checked: CheckerProgress
) -> CheckerProgress:
    """The progress to save after a check that began from `start`, with `stored` saved by
    then and `checked` what this check reached.

    - Message IDs and first searches: both kept.
    - A Drive file's version: the stored one when another check's sink changed it during
      this check, else this check's. So a v2 this check skipped (too large, say), which
      no sink saves, isn't tried again on every check.
    - The mailbox position: the later one, never back.
    """

    def by_file(p: CheckerProgress) -> dict[tuple[str, str], DriveVersion]:
        return {(v.grant_id, v.drive_file_id): v for v in p.drive_versions}

    began, saved = by_file(start), by_file(stored)
    versions = saved | by_file(checked)
    versions |= {k: v for k, v in saved.items() if began.get(k) != v}
    return CheckerProgress(
        mail_cursor=_later_cursor(checked.mail_cursor, stored.mail_cursor),
        seen_message_ids=tuple(sorted({*stored.seen_message_ids, *checked.seen_message_ids})),
        drive_versions=tuple(versions[k] for k in sorted(versions)),
        first_search_done=tuple(sorted({*stored.first_search_done, *checked.first_search_done})),
    )
