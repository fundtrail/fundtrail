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
from .email_files import email_to_files, parse_headers
from .incoming import GrantRoute, HeldMail, HoldReason, IncomingFile
from .sources import DriveSource, MailSource, RawMessage

log = logging.getLogger(__name__)

# How often the timer checks, in seconds: inside the one to two minutes of decision 0013.
CHECK_INTERVAL_SECONDS = 90


class IngestSink(Protocol):
    def store(self, files: list[IncomingFile]) -> None:
        """Store arrived files. A message comes first, then its attachments."""
        ...

    def hold(self, held: HeldMail) -> None: ...


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
    """
    routes = list(routes)
    by_tag = {route.tag.lower(): route for route in routes}
    # The position is read first, so nothing delivered during the first reads is missed.
    messages, state.mail_cursor = source.fetch_new(state.mail_cursor)
    for route in routes:
        if route.grant_id in state.started_grants:
            continue
        address = grant_address(mailbox, route.tag)
        for message in source.fetch_delivered_to(address, route.address_created_at):
            _take(message, mailbox, by_tag, state, now, sink, authserv_id)
        state.started_grants.add(route.grant_id)
    for message in messages:
        _take(message, mailbox, by_tag, state, now, sink, authserv_id)


def _take(
    message: RawMessage,
    mailbox: str,
    by_tag: dict[str, GrantRoute],
    state: CheckState,
    now: WorkspaceNow,
    sink: IngestSink,
    authserv_id: str,
) -> None:
    if message.id in state.seen_messages:
        return
    state.seen_messages.add(message.id)
    parsed = parse_headers(message.raw)
    tag = find_tag(parsed.headers, mailbox)
    route = by_tag.get(tag) if tag else None
    if route is None:
        log.info("ignored a message with no tag or an unknown one")
        return
    files = email_to_files(
        message.raw,
        message_id=message.id,
        grant_id=route.grant_id,
        workspace_id=route.workspace_id,
    )
    at = now(route.workspace_id)
    reason: HoldReason | None = None
    if not parsed.sender or parsed.sender not in route.known_senders:
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
            gmail_message_id=message.id,
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
    real_now = real_now or datetime.now(UTC)
    for route in routes:
        if not route.drive_folder_id:
            continue
        entries = source.list_tree(route.drive_folder_id)
        for entry in files_to_take(
            entries, grant_id=route.grant_id, state=state.drive, real_now=real_now
        ):
            try:
                incoming = drive_file(
                    source, entry, grant_id=route.grant_id, workspace_id=route.workspace_id
                )
            except Exception:
                log.exception("could not read a Drive file; it's tried again next check")
                continue
            sink.store([incoming.arriving(now(route.workspace_id))])
            state.drive.taken[(route.grant_id, entry.id)] = version_of(entry)


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
