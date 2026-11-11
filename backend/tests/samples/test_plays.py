"""The two plays of each sample (issue 165), in CI with no paid calls: doing nothing, with
the agent writing nothing; and doing everything the script says, checks only, with the
sample's hand-written agent records in place of the live agent's."""

from __future__ import annotations

import json

import pytest

from app.contracts.runs import RunStatus
from app.contracts.workspaces import Grant
from app.db import store
from app.db.pool import transaction
from app.db.ports import ModuleChecks
from app.samples import player
from app.samples.pack import LARGER_SAMPLE, SMALL_SAMPLE
from tests.api.conftest import Api
from tests.db.platform_fixtures import run_worker_until_idle

from .plays import act_through_api, checks_at, play_everything, play_nothing
from .test_player import _open, _workspace

CHOICE = {SMALL_SAMPLE: "small_live", LARGER_SAMPLE: "larger_live"}


@pytest.fixture
def real_checks(api: Api) -> None:
    api.platform.checks = ModuleChecks()


def _grant(api: Api, grant_id: str) -> Grant:
    with transaction(api.platform.pool) as conn:
        grant = store.get_grant(conn, grant_id)
    assert grant is not None
    return grant


@pytest.mark.parametrize("sample", [SMALL_SAMPLE, LARGER_SAMPLE])
def test_doing_nothing_plays_every_event_without_an_error(
    api: Api, real_checks: None, sample: str
) -> None:
    grant = _grant(api, _open(api, CHOICE[sample]))
    moves = play_nothing(api.platform, api.user_id, grant, after_each_move=lambda: None)
    run_worker_until_idle(str(api.platform.pool.conninfo))
    pack = player.pack_for(sample)
    assert moves > 0
    with transaction(api.platform.pool) as conn:
        now = store.get_grant(conn, grant.id)
        files = store.list_files(conn, grant.id, store.END_OF_TIME)
        charges = store.list_charges(conn, grant.id, store.END_OF_TIME)
        runs = store.list_runs(conn, grant.id)
    assert now is not None and now.clock_now == max(i.at for i in player.items_for(sample))
    scheduled = {e.name for e in pack.events if e.kind.value == "file" and not e.deliver_by_user}
    # Every scheduled file arrives, or, for an email from a sender who isn't known, is held
    # (ruling 58): with nobody confirming terms, nobody named in them is known.
    with transaction(api.platform.pool) as conn:
        held = {
            h.files[0].sha256
            for h in store.list_held_mail(conn, grant.workspace_id, store.END_OF_TIME)
        }
    assert {pack.sha256(n) for n in scheduled} <= {f.sha256 for f in files} | held
    # The user's marked files never arrive: the clock never delivers them (ruling 44).
    marked = {pack.sha256(e.name) for e in pack.events if e.deliver_by_user}
    assert not marked & {f.sha256 for f in files}
    assert {c.ledger_line_id for c in charges} == set(pack.ledger_line_ids())
    assert runs and {r.status for r in runs} == {RunStatus.DONE}
    # The real checks run once at the end, over everything, without an error.
    assert now.clock_now is not None
    seen, output = checks_at(api.platform, grant, now.clock_now)
    assert {s.charge_id for s in output.charges} == {c.id for c in seen}


@pytest.mark.parametrize("sample", [SMALL_SAMPLE, LARGER_SAMPLE])
def test_doing_everything_gives_the_keys_buckets(api: Api, real_checks: None, sample: str) -> None:
    grant = _grant(api, _open(api, CHOICE[sample]))
    result = play_everything(
        api.platform, api.user_id, grant, act_through_api(api), after_each_move=lambda: None
    )
    key = json.loads((player.pack_for(sample).folder / "answer_key.json").read_text())
    assert result.checked == len(key["buckets"])
    assert result.wrong == []


def test_two_copies_in_one_workspace_each_get_their_own_records(
    api: Api, real_checks: None
) -> None:
    """Placeholder IDs map to each grant's own charges and files (ruling 56)."""
    workspace_id = _workspace(api)
    first = _grant(api, _open(api, "small_live", workspace_id))
    second = _grant(api, _open(api, "small_live", workspace_id))
    for grant in (first, second):
        result = play_everything(
            api.platform, api.user_id, grant, act_through_api(api), after_each_move=lambda: None
        )
        assert result.wrong == []
    with transaction(api.platform.pool) as conn:
        for grant in (first, second):
            charges = {c.id for c in store.list_charges(conn, grant.id, store.END_OF_TIME)}
            links = [r for r in store.list_records(conn, grant.id) if r.kind.value == "link"]
            assert links and all(r.charge_id in charges for r in links)
