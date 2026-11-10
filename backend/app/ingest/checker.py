"""Checking Gmail and Drive on a timer (decisions 0013, 0023 and 0025).

The timer runs on real time. What it brings in arrives at the workspace's "now",
which the caller supplies, because the workspace clock is not this module's.

Storing waits on the contract additions in issue 39: the caller passes an
`IngestSink` that stores arrived files and held mail.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from .addresses import find_tag, grant_address
from .authentication import GMAIL_AUTHSERV_ID, is_verified
from .drive_files import DriveState, drive_file, files_to_take, version_of
from .email_files import ParsedEmail, email_parts, parse_headers
from .incoming import GrantRoute, HeldMail, HoldReason, IncomingFile, SkippedFile
from .sources import CannotTake, DriveSource, MailSource, RawMessage

log = logging.getLogger(__name__)

# How often the timer checks, in seconds: inside the one to two minutes of decision 0013.
CHECK_INTERVAL_SECONDS = 90


class IngestSink(Protocol):
    def store(self, files: list[IncomingFile]) -> None:
        """Store arrived files. A message comes first, then its attachments."""
        ...

    def hold(self, held: HeldMail) -> None: ...

    def skip(self, skipped: SkippedFile) -> None:
        """Record a file that was sent but not taken in, so the grant shows a problem."""
        ...


# The workspace's "now", given its ID.
WorkspaceNow = Callable[[str], datetime]


@dataclass
class CheckState:
    """What the checker remembers between checks. Saved by the caller."""

    mail_cursor: str | None = None
    started_grants: set[str] = field(default_factory=set)  # grants whose first read is done
    seen_messages: set[str] = field(default_factory=set)
    drive: DriveState = field(default_factory=DriveState)


def check_mail(
    source: MailSource,
    *,
    mailbox: str,
    routes: Iterable[GrantRoute],
    state: CheckState,
    now: WorkspaceNow,
    sink: IngestSink,
    authserv_id: str = GMAIL_AUTHSERV_ID,
) -> None:
    """Take in new mail for every grant.

    A grant's first check reads everything delivered to its address since the address
    was made. After that, the mailbox's saved position finds what's new. Mail never
    sent to a grant's address is never taken in; the accountant forwards it.

    A message is marked seen only once it has been stored or held, and the saved
    position moves only when every message in the batch was, so a failure loses nothing:
    the next check reads the batch again and skips what it already took.
    """
    routes = list(routes)
    by_tag = {route.tag: route for route in routes}
    # The position is read first, so nothing delivered during the first reads is missed.
    messages, next_cursor = source.fetch_new(state.mail_cursor)
    for route in routes:
        if route.grant_id in state.started_grants:
            continue
        address = grant_address(mailbox, route.tag)
        try:
            found = source.fetch_delivered_to(address, route.address_created_at)
        except Exception:
            log.exception("could not read a grant's earlier mail; tried again next check")
            continue
        if all([_take(m, mailbox, by_tag, state, now, sink, authserv_id) for m in found]):
            state.started_grants.add(route.grant_id)
    if all([_take(m, mailbox, by_tag, state, now, sink, authserv_id) for m in messages]):
        state.mail_cursor = next_cursor


def _take(
    message: RawMessage,
    mailbox: str,
    by_tag: dict[str, GrantRoute],
    state: CheckState,
    now: WorkspaceNow,
    sink: IngestSink,
    authserv_id: str,
) -> bool:
    """Store or hold one message. False when it failed and has to be tried again."""
    if message.id in state.seen_messages:
        return True
    try:
        taken = _store_or_hold(message, mailbox, by_tag, now, sink, authserv_id)
    except Exception:
        log.exception("could not take in a message; tried again next check")
        return False
    # A message no grant's route knows yet isn't marked seen: if its grant's route turns
    # up later, that grant's first read takes it in.
    if taken:
        state.seen_messages.add(message.id)
    return True


def _store_or_hold(
    message: RawMessage,
    mailbox: str,
    by_tag: dict[str, GrantRoute],
    now: WorkspaceNow,
    sink: IngestSink,
    authserv_id: str,
) -> bool:
    """Store or hold one message. False when no grant's route knows its address."""
    parsed = parse_headers(message.raw)
    tag = find_tag(parsed.headers, mailbox)
    route = by_tag.get(tag) if tag else None
    if route is None:
        log.info("ignored a message with no tag or an unknown one")
        return False
    parts = email_parts(
        message.raw,
        message_id=message.id,
        grant_id=route.grant_id,
        workspace_id=route.workspace_id,
    )
    files = parts.files
    at = now(route.workspace_id)
    _arrive_or_hold(parsed, route, message.id, files, at, sink, authserv_id)
    # Reported whether the message arrives or is held: either way the accountant sent it.
    # Reported after the message is stored, so a retry doesn't report it twice.
    for skipped in parts.skipped:
        sink.skip(skipped.at(at))
    return True


def _arrive_or_hold(
    parsed: ParsedEmail,
    route: GrantRoute,
    message_id: str,
    files: list[IncomingFile],
    at: datetime,
    sink: IngestSink,
    authserv_id: str,
) -> None:
    reason: HoldReason | None = None
    if parsed.sender is None:
        reason = "unverified_sender"  # the From line isn't exactly one readable address
    elif parsed.sender not in route.known_senders:
        reason = "unknown_sender"
    elif not is_verified(parsed.headers, parsed.sender, authserv_id):
        # A forwarded message is judged on the forwarder, whose address is in From.
        reason = "unverified_sender"
    if reason is None:
        sink.store([f.arriving(at) for f in files])
        return
    sink.hold(
        HeldMail(
            grant_id=route.grant_id,
            workspace_id=route.workspace_id,
            sender=parsed.sender,
            from_header=parsed.from_header,
            gmail_message_id=message_id,
            files=tuple(files),
            held_at=at,
            reason=reason,
        )
    )


def check_drive(
    source: DriveSource,
    *,
    routes: Iterable[GrantRoute],
    state: CheckState,
    now: WorkspaceNow,
    sink: IngestSink,
    real_now: datetime | None = None,
) -> None:
    """Take in new and modified files from each grant's folder.

    One grant's failure, such as a folder no longer shared, doesn't stop the others.
    """
    real_now = real_now or datetime.now(UTC)
    for route in routes:
        if not route.drive_folder_id:
            continue
        try:
            _check_folder(source, route, route.drive_folder_id, state, now, sink, real_now)
        except Exception:
            log.exception("could not read a grant's Drive folder; tried again next check")


def _check_folder(
    source: DriveSource,
    route: GrantRoute,
    folder_id: str,
    state: CheckState,
    now: WorkspaceNow,
    sink: IngestSink,
    real_now: datetime,
) -> None:
    entries = source.list_tree(folder_id)
    for entry in files_to_take(
        entries, grant_id=route.grant_id, state=state.drive, real_now=real_now
    ):
        key = (route.grant_id, entry.id)
        try:
            incoming = drive_file(
                source, entry, grant_id=route.grant_id, workspace_id=route.workspace_id
            )
            sink.store([incoming.arriving(now(route.workspace_id))])
        except CannotTake as cannot:
            # Reported, and not tried again until the file changes.
            sink.skip(
                SkippedFile(
                    grant_id=route.grant_id,
                    workspace_id=route.workspace_id,
                    name=entry.name,
                    source="drive",
                    message_or_folder=folder_id,
                    reason=cannot.reason,
                    source_ref=entry.id,
                    skipped_at=now(route.workspace_id),
                )
            )
        except Exception:
            log.exception("could not take in a Drive file; tried again next check")
            continue
        state.drive.taken[key] = version_of(entry)


def check_once(
    *,
    mail: MailSource | None,
    drive: DriveSource | None,
    mailbox: str,
    routes: list[GrantRoute],
    state: CheckState,
    now: WorkspaceNow,
    sink: IngestSink,
) -> None:
    """One check of both. A failure in one doesn't stop the other."""
    if mail is not None:
        try:
            check_mail(mail, mailbox=mailbox, routes=routes, state=state, now=now, sink=sink)
        except Exception:
            log.exception("the mail check failed")
    if drive is not None:
        try:
            check_drive(drive, routes=routes, state=state, now=now, sink=sink)
        except Exception:
            log.exception("the Drive check failed")


async def run_checks_forever(
    check: Callable[[], None], interval: float = CHECK_INTERVAL_SECONDS
) -> None:
    """Run `check` now and then every `interval` seconds of real time, off the event loop."""
    while True:
        try:
            await asyncio.to_thread(check)
        except Exception:
            log.exception("a check failed")
        await asyncio.sleep(interval)
