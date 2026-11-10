"""Procrastinate's schema migration: the worker's startup queries run on a migrated database.

The queries below are the ones Procrastinate 3.10.0 sends (its sql/queries.sql) when a
worker starts, takes a job, beats and stops. They run here without the library, so the
migration is checked even where Procrastinate isn't installed. Where it is, the last two
tests also run the library's own job manager and compare the migration with its schema.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import psycopg
else:
    psycopg = pytest.importorskip("psycopg")

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / "supabase"
    / "migrations"
    / "20261110210000_procrastinate_schema.sql"
)
PROCRASTINATE_TABLES = [
    "procrastinate_events",
    "procrastinate_jobs",
    "procrastinate_periodic_defers",
    "procrastinate_workers",
]


def test_the_worker_starts_takes_a_job_and_stops(db: psycopg.Connection) -> None:
    # check_connection
    assert db.execute("select to_regclass('procrastinate_jobs') as check").fetchone() == (
        "procrastinate_jobs",
    )
    # Worker.run: prune stalled workers, then register.
    db.execute("select * from procrastinate_prune_stalled_workers_v1(%s)", [30.0]).fetchall()
    row = db.execute("select * from procrastinate_register_worker_v1()").fetchone()
    assert row is not None
    worker_id = row[0]
    # listen_for_jobs
    db.execute("listen procrastinate_any_queue_v1")
    db.execute('listen "procrastinate_queue_v1#agent"')
    # defer_jobs, as the platform queues a run
    job = db.execute(
        "select unnest(procrastinate_defer_jobs_v1(array[row("
        "'agent', 'run_agent', 0, 'grant-1', null, '{}'::jsonb, null"
        ")::procrastinate_job_to_defer_v1])) as id"
    ).fetchone()
    assert job is not None
    # fetch_job
    fetched = db.execute(
        "select id, status, task_name, priority, lock, queueing_lock, args, scheduled_at, "
        "queue_name, attempts, worker_id "
        "from procrastinate_fetch_job_v2(%s::varchar[], %s)",
        [["agent"], worker_id],
    ).fetchone()
    assert fetched is not None
    assert (fetched[0], fetched[1], fetched[10]) == (job[0], "doing", worker_id)
    # update_heartbeat, list_jobs_to_abort, finish_job, unregister_worker
    db.execute("select procrastinate_update_heartbeat_v1(%s)", [worker_id])
    aborting = db.execute(
        "select id from procrastinate_jobs where status = 'doing' and abort_requested = true "
        "and (%s::varchar is null or queue_name = %s)",
        [None, None],
    ).fetchall()
    assert aborting == []
    db.execute("select procrastinate_finish_job_v1(%s, %s, %s)", [job[0], "succeeded", False])
    db.execute("select procrastinate_unregister_worker_v1(%s)", [worker_id])
    status = db.execute("select status from procrastinate_jobs where id = %s", [job[0]])
    assert status.fetchone() == ("succeeded",)


def test_the_job_tables_have_row_level_security_and_no_policies(db: psycopg.Connection) -> None:
    rows = db.execute(
        "select relname, relrowsecurity from pg_class "
        "where relnamespace = 'public'::regnamespace and relkind = 'r' "
        "and relname like 'procrastinate\\_%' order by relname"
    ).fetchall()
    assert rows == [(table, True) for table in PROCRASTINATE_TABLES]
    policies = db.execute(
        "select count(*) from pg_policies where tablename like 'procrastinate\\_%'"
    ).fetchone()
    assert policies == (0,)


def test_the_migration_is_procrastinates_own_schema() -> None:
    schema = pytest.importorskip("procrastinate.schema")
    text = MIGRATION.read_text()
    match = re.search(
        r"^-- BEGIN procrastinate 3\.10\.0 schema\n(.*)^-- END procrastinate 3\.10\.0 schema\n",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    assert match.group(1).strip() == schema.SchemaManager.get_schema().strip()


def test_procrastinates_job_manager_starts_a_worker(database_url: str) -> None:
    procrastinate = pytest.importorskip("procrastinate")

    async def start_and_stop() -> None:
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=database_url))
        async with app.open_async():
            manager = app.job_manager
            await manager.prune_stalled_workers(30.0)
            worker_id = await manager.register_worker()
            await manager.update_heartbeat(worker_id)
            await manager.unregister_worker(worker_id)

    asyncio.run(start_and_stop())
