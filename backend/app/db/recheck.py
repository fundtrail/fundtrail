"""Rerun every check on a grant and write a status row for each status that changed.

Code reruns the checks whenever a record changes, a charge or file arrives, or a run
saves or fails for good. There's no agent call here. Each new status row carries its
trigger; for a change that comes from saving an agent run, that's what started the run.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from app.contracts.checks import ChecksInput, ChecksOutput, GrantStatus, RecordStatus
from app.contracts.rules import RecordState, award_number_and_title
from app.contracts.runs import Trigger
from app.contracts.workspaces import Grant

from . import store
from .ports import Checks
from .store import Conn, Status


def recheck_grant(
    conn: Conn,
    checks: Checks,
    grant: Grant,
    now: datetime,
    trigger: Trigger,
    *,
    charge_triggers: Mapping[str, Trigger] | None = None,
    file_triggers: Mapping[str, Trigger] | None = None,
) -> ChecksOutput:
    """Run the checks on everything on the grant visible at `now` and write what changed.

    `charge_triggers` gives a charge its own trigger, such as the charge itself when a
    ledger upload adds it; every other change gets `trigger`.
    """
    records = store.list_records(conn, grant.id, now)
    files = store.list_files(conn, grant.id, now)
    output = checks.run_checks(
        ChecksInput(
            now=now,
            charges=tuple(store.list_charges(conn, grant.id, now)),
            files=tuple(files),
            records=tuple(records),
            failed_runs=tuple(store.failed_runs(conn, grant.id)),
            skipped_files=tuple(store.list_skipped(conn, grant.id, now)),
        )
    )
    # The grant's award number and title follow the notices that count (issue 118).
    number, title = award_number_and_title(RecordState(records, files))
    store.set_award_number_and_title(conn, grant.id, number, title)
    statuses: list[Status] = [
        *(s for s in output.charges if s.grant_id == grant.id),
        *(s for s in output.records if s.grant_id == grant.id),
        *(s for s in output.grants if s.grant_id == grant.id),
    ]
    # Compared with each status as it stood at `now`, which matters when a catch-up
    # works out a moment before the latest row: only a real change at that moment
    # gets a row.
    current = store.statuses_as_of(conn, grant.id, now)
    for status in statuses:
        key = store.status_key(status)
        old = current.pop(key, None)
        if old is not None and store.same_status(old, status):
            continue
        own = {"charge": charge_triggers or {}, "file": file_triggers or {}}.get(key[0], {}).get(
            key[1] or ""
        )
        store.insert_status(conn, grant.workspace_id, status, now, own or trigger)
    # A record, file or grant whose problem went away has no status in the output.
    # Write a cleared one, so its latest status no longer shows the old problem.
    for old in current.values():
        if isinstance(old, RecordStatus) and (old.problems or old.flagged):
            cleared = RecordStatus(
                grant_id=grant.id,
                record_id=old.record_id,
                file_id=old.file_id,
                problems=(),
                flagged=False,
            )
            store.insert_status(conn, grant.workspace_id, cleared, now, trigger)
        elif isinstance(old, GrantStatus) and (old.problems or old.flagged):
            store.insert_status(
                conn,
                grant.workspace_id,
                GrantStatus(grant_id=grant.id, problems=(), flagged=False),
                now,
                trigger,
            )
    return output
