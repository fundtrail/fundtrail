"""Checking Gmail and Drive on a timer (decisions 0013, 0023 and 0025).

The timer runs on real time. What it brings in arrives at the workspace's "now",
which the caller supplies, because the workspace clock is not this module's.

The caller passes an `IngestSink` that stores arrived files, held mail and skipped
files, and saves the checker's progress (the contract's `CheckerProgress`) after each
check with `CheckState.to_progress`.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.contracts.mail import CheckerProgress, DriveVersion, HoldReason, SkippedFile, SkipReason

from .addresses import find_tag, grant_address
from .authentication import GMAIL_AUTHSERV_ID, is_verified
from .drive_files import DriveState, drive_file, files_to_take, version_of
from .email_files import EmailParts, ParsedEmail, email_parts, parse_headers
from .incoming import GrantRoute, IncomingFile, PendingHold, to_skipped_file
from .sources import CannotTake, DriveSource, MailSource, RawMessage

log = logging.getLogger(__name__)

# How often the timer checks, in seconds: inside the one to two minutes of decision 0013.
CHECK_INTERVAL_SECONDS = 90


class IngestSink(Protocol):
    def store(self, files: list[IncomingFile], skipped: Sequence[SkippedFile] = ()) -> None:
        """Store arrived files, a message first and then its attachments, in one write with
        the message's skipped attachments. One write, so a message is stored once even if
        saving its skips fails: the whole message is tried again."""
        ...

    def hold(self, held: PendingHold) -> None:
        """Store a held message's files and save the contract's `HeldMail`
        (`to_held_mail`), with its skipped files, in one write."""
        ...

    def skip(self, skipped: SkippedFile) -> None:
        """Record a Drive file that wasn't taken in, so the grant shows a problem."""
        ...


# The workspace's "now", given its ID.
WorkspaceNow = Callable[[str], datetime]


@dataclass
class CheckState:
    """The checker's working copy of the contract's `CheckerProgress`.

    It's loaded with `from_progress` before a check and saved with `to_progress` after.
    """

    mail_cursor: str | None = None
    # Grants whose first search of their address has finished: added only once every
    # message it found was stored or held, so a search cut off partway is redone in full.
    first_search_done: set[str] = field(default_factory=set)
    seen_messages: set[str] = field(default_factory=set)
    drive: DriveState = field(default_factory=DriveState)

    @classmethod
    def from_progress(cls, progress: CheckerProgress) -> "CheckState":
        return cls(
            mail_cursor=progress.mail_cursor,
            first_search_done=set(progress.first_search_done),
            seen_messages=set(progress.seen_message_ids),
            drive=DriveState(
                taken={(v.grant_id, v.drive_file_id): v.version for v in progress.drive_versions}
            ),
        )

    def to_progress(self) -> CheckerProgress:
        return CheckerProgress(
            mail_cursor=self.mail_cursor,
            seen_message_ids=tuple(sorted(self.seen_messages)),
            drive_versions=tuple(
                DriveVersion(grant_id=grant_id, drive_file_id=file_id, version=version)
                for (grant_id, file_id), version in sorted(self.drive.taken.items())
            ),
            first_search_done=tuple(sorted(self.first_search_done)),
        )


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
        if route.grant_id in state.first_search_done:
            continue
        address = grant_address(mailbox, route.tag)
        try:
            found = source.fetch_delivered_to(address, route.address_created_at)
        except Exception:
            log.exception("could not read a grant's earlier mail; tried again next check")
            continue
        if all([_take(m, mailbox, by_tag, state, now, sink, authserv_id) for m in found]):
            state.first_search_done.add(route.grant_id)
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
    _arrive_or_hold(parsed, route, message.id, parts, now(route.workspace_id), sink, authserv_id)
    return True


def _arrive_or_hold(
    parsed: ParsedEmail,
    route: GrantRoute,
    message_id: str,
    parts: EmailParts,
    at: datetime,
    sink: IngestSink,
    authserv_id: str,
) -> None:
    """Store the message, or hold it.

    Skipped attachments are reported with mail that arrives, in the same write. Held
    mail keeps them, and they're reported if it's let in (`let_in_skips`): no check uses
    held mail (0025), so a stranger can't put a problem on the grant.
    """
    files = parts.files
    skipped = [to_skipped_file(found, at) for found in parts.skipped]
    reason: HoldReason | None = None
    if parsed.sender is None:
        reason = HoldReason.UNVERIFIED_SENDER  # the From line isn't exactly one address
    elif parsed.sender not in route.known_senders:
        reason = HoldReason.UNKNOWN_SENDER
    elif not is_verified(parsed.headers, parsed.sender, authserv_id):
        # A forwarded message is judged on the forwarder, whose address is in From.
        reason = HoldReason.UNVERIFIED_SENDER
    if reason is None:
        sink.store([f.arriving(at) for f in files], skipped)
        return
    sink.hold(
        PendingHold(
            workspace_id=route.workspace_id,
            grant_id=route.grant_id,
            sender=parsed.sender,
            from_header=parsed.from_header,
            gmail_message_id=message_id,
            subject=parsed.subject or None,
            files=tuple(files),
            held_at=at,
            reason=reason,
            skipped=tuple(skipped),
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
                    source_ref=folder_id,
                    reason=SkipReason(cannot.reason),
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
