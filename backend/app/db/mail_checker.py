"""The Gmail and Drive checker on a timer (decisions 0013 and 0025).

The job worker runs `run` every minute. One checker runs at a time: the job takes a
Procrastinate lock, and `run` also holds a database advisory lock for the whole check,
so a second checker started anywhere finds it taken and does nothing.

Each grant with an email address is a route: its tag, its Drive folder, its known senders
(`held_mail.known_senders`, the same ones let-in uses), and whether its channel times come
from the grant's clock (a sample grant, `clock.has_stored_clock`). Arrivals are dated by
each grant's clock (`clock.grant_clock`).

Nothing is checked until the Google account file (`GOOGLE_TOKEN_FILE`) and the app's
mailbox address (`FUNDTRAIL_MAILBOX`) are set.
"""

from __future__ import annotations

import logging
import os

from app.contracts.rules import RecordState
from app.ingest.incoming import GrantRoute
from app.ingest.sources import DriveSource, MailSource

from . import clock, held_mail, mail_sink, store
from .platform import Platform
from .pool import transaction
from .store import Conn

log = logging.getLogger(__name__)

# The advisory lock one checker holds for a whole check.
LOCK_KEY = "fundtrail.mail_checker"


def routes(conn: Conn) -> list[GrantRoute]:
    """A route for each grant that has an email address."""
    out: list[GrantRoute] = []
    for grant in store.all_grants(conn):
        if not grant.address_code:
            continue  # no address yet, so nothing to check
        now = clock.grant_now(conn, grant.id)
        state = RecordState(store.list_records(conn, grant.id, now))
        out.append(
            GrantRoute(
                workspace_id=grant.workspace_id,
                grant_id=grant.id,
                tag=grant.address_code,
                drive_folder_id=grant.drive_folder_id,
                known_senders=frozenset(held_mail.known_senders(conn, grant, state)),
                channel_times_from_grant_now=clock.has_stored_clock(conn, grant.id),
            )
        )
    return out


def _google_sources() -> tuple[MailSource, DriveSource] | None:
    if not os.environ.get("GOOGLE_TOKEN_FILE"):
        return None
    from app.ingest.google_clients import GmailMailbox, GoogleDrive, load_credentials

    credentials = load_credentials()
    return GmailMailbox(credentials), GoogleDrive(credentials)


def run(
    p: Platform,
    *,
    mail: MailSource | None = None,
    drive: DriveSource | None = None,
    mailbox: str | None = None,
) -> bool:
    """One check, unless another checker holds the lock or nothing is set up. True when
    it checked. Sources and the mailbox come from the environment unless given."""
    mailbox = mailbox or os.environ.get("FUNDTRAIL_MAILBOX")
    if mail is None and drive is None:
        sources = _google_sources()
        if sources is None or not mailbox:
            log.info("the mail checker isn't set up (GOOGLE_TOKEN_FILE, FUNDTRAIL_MAILBOX)")
            return False
        mail, drive = sources
    with p.pool.connection() as lock_conn:
        row = lock_conn.execute(
            "select pg_try_advisory_lock(hashtext(%s)) as got", (LOCK_KEY,)
        ).fetchone()
        # A session-level lock outlives its transaction: committing now leaves the
        # connection idle, not idle in a transaction, for the whole check, so an
        # idle-transaction timeout can't end the session and drop the lock mid-check.
        lock_conn.commit()
        if row is None or not row["got"]:
            log.info("another mail checker is running")
            return False
        try:
            with transaction(p.pool) as conn:
                found = routes(conn)
            mail_sink.check_and_save(p, mail=mail, drive=drive, mailbox=mailbox or "", routes=found)
        finally:
            lock_conn.execute("select pg_advisory_unlock(hashtext(%s))", (LOCK_KEY,))
            lock_conn.commit()
    return True
