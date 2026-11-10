"""The two plays of each sample (issue 165), in CI with no paid calls: doing nothing, with
the agent writing nothing; and doing everything the script says, checks only, with the
sample's hand-written agent records in place of the live agent's."""

from __future__ import annotations

import json
import mimetypes

import pytest

from app.contracts.runs import RunStatus
from app.contracts.workspaces import Grant
from app.db import store
from app.db.pool import transaction
from app.db.ports import ModuleChecks
from app.samples import player
from app.samples.pack import LARGER_SAMPLE, SMALL_SAMPLE, UserAction
from tests.api.conftest import Api
from tests.db.platform_fixtures import run_worker_until_idle

from .plays import Mapping, play_everything, play_nothing, terms_from
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


def _act(api: Api):
    """The user's scripted actions, through the API's ordinary routes."""

    def act(grant: Grant, action: UserAction, mapping: Mapping) -> None:
        assert action.file is not None
        if action.action == "confirm_terms":
            with transaction(api.platform.pool) as conn:
                file_id = mapping(conn, f"file-{action.file}")
            ids = terms_from(api.platform, grant, file_id)
            assert ids, f"no terms from {action.file} wait to be confirmed"
            response = api.client.post(
                f"/grants/{grant.id}/records",
                json={"data": {"kind": "confirmation", "record_ids": ids}},
                headers=api.headers,
            )
        elif action.action == "deliver_file":
            data = mapping.pack.file_bytes(action.file)
            media_type = mimetypes.guess_type(action.file)[0] or "application/octet-stream"
            response = api.client.post(
                f"/grants/{grant.id}/evidence",
                files={"file": (action.file, data, media_type)},
                headers=api.headers,
            )
        else:
            raise AssertionError(f"the play doesn't do {action.action} yet")
        assert response.status_code == 201, response.text

    return act


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
    assert {pack.sha256(n) for n in scheduled} <= {f.sha256 for f in files}
    assert {c.ledger_line_id for c in charges} == set(pack.ledger_line_ids())
    assert runs and {r.status for r in runs} == {RunStatus.DONE}


@pytest.mark.parametrize("sample", [SMALL_SAMPLE, LARGER_SAMPLE])
def test_doing_everything_gives_the_keys_buckets(api: Api, real_checks: None, sample: str) -> None:
    grant = _grant(api, _open(api, CHOICE[sample]))
    result = play_everything(
        api.platform, api.user_id, grant, _act(api), after_each_move=lambda: None
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
            api.platform, api.user_id, grant, _act(api), after_each_move=lambda: None
        )
        assert result.wrong == []
    with transaction(api.platform.pool) as conn:
        for grant in (first, second):
            charges = {c.id for c in store.list_charges(conn, grant.id, store.END_OF_TIME)}
            links = [r for r in store.list_records(conn, grant.id) if r.kind.value == "link"]
            assert links and all(r.charge_id in charges for r in links)
