"""The accountant script's steps (rulings 47, 51 and 59), on a small fixture pack: the
contracts' golden sample grant (contracts.md section 15) laid out as a sample folder.

Each step resolves against what's on the grant (app.samples.script) and goes through the
app's ordinary routes as the test user. A step whose target isn't there resolves to None:
it's left for the user.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.contracts.fixtures import DOCUMENTS_DIR, LEDGER_FILE, SampleGrant
from app.contracts.records import (
    Answer,
    Author,
    CitedText,
    Judgment,
    MailDecision,
    Question,
    Record,
    Remainder,
)
from app.contracts.rules import RecordState
from app.db import store
from app.db.pool import transaction
from app.db.ports import ModuleChecks
from app.samples.pack import PackError, SamplePack, load_folder
from app.samples.script import DeliverFile, SignOff, WriteRecord, resolve
from tests.api.conftest import Api
from tests.db.platform_fixtures import sample_into_db

from .plays import Mapping, act_through_api

APRIL_9 = datetime(2026, 4, 9, 17, tzinfo=UTC)  # the extension waits to be confirmed

EVENTS = [
    {"at": "2023-01-12T15:00:00Z", "kind": "file", "file": "award_letter.txt", "source": "upload"},
    {"at": "2025-11-12T18:00:00Z", "kind": "file", "file": "invoice_1001.txt", "source": "upload"},
    {"at": "2025-11-14T00:00:00Z", "kind": "ledger_line", "line_id": "L-1001"},
    {
        "at": "2026-02-21T17:30:00Z",
        "kind": "file",
        "file": "sequencing_statement.eml",
        "source": "gmail",
        "sender": "robin.example@university.example",
    },
    {"at": "2026-02-24T00:00:00Z", "kind": "ledger_line", "line_id": "L-1002"},
    {
        "at": "2026-04-09T16:00:00Z",
        "kind": "file",
        "file": "extension_notice.txt",
        "source": "drive",
    },
]


def golden_pack(folder: Path, actions: list[dict[str, Any]]) -> SamplePack:
    folder.mkdir(parents=True, exist_ok=True)
    for f in DOCUMENTS_DIR.iterdir():
        shutil.copy(f, folder / f.name)
    shutil.copy(LEDGER_FILE, folder / "ledger.csv")
    timeline = {"sample": "golden", "starts_at": EVENTS[0]["at"], "events": EVENTS}
    (folder / "timeline.json").write_text(json.dumps(timeline))
    (folder / "user_actions.json").write_text(json.dumps({"sample": "golden", "actions": actions}))
    return load_folder(folder)


def step(at: datetime, action: str, **fields: Any) -> dict[str, Any]:
    return {"at": at.isoformat().replace("+00:00", "Z"), "action": action, **fields}


@pytest.fixture
def golden(api: Api) -> SampleGrant:
    api.platform.checks = ModuleChecks()
    return sample_into_db(api.platform, api.user_id, APRIL_9)


def _resolve(api: Api, sample: SampleGrant, pack: SamplePack) -> Any:
    [action] = pack.actions
    with transaction(api.platform.pool) as conn:
        return resolve(api.platform, conn, sample.grant, pack, action, action.at)


def _act(api: Api, sample: SampleGrant, pack: SamplePack) -> None:
    [action] = pack.actions
    act_through_api(api)(sample.grant, action, Mapping(pack, sample.grant))


def _records(api: Api, sample: SampleGrant, at: datetime = APRIL_9) -> list[Record]:
    with transaction(api.platform.pool) as conn:
        return store.list_records(conn, sample.grant.id, at)


def _state(api: Api, sample: SampleGrant) -> RecordState:
    with transaction(api.platform.pool) as conn:
        return RecordState(
            store.list_records(conn, sample.grant.id, APRIL_9),
            store.list_files(conn, sample.grant.id, APRIL_9),
        )


def _insert(api: Api, sample: SampleGrant, data: Any, written_at: datetime) -> str:
    """An agent record, stored as a run at `written_at` would store it."""
    from app.contracts.rules import run_read_point

    with transaction(api.platform.pool) as conn:
        record = Record(
            id=f"rec-{data.kind}-{written_at.timestamp():.0f}-{sample.grant.id[-6:]}",
            workspace_id=sample.grant.workspace_id,
            grant_id=sample.grant.id,
            author=Author.AGENT,
            written_at=written_at,
            read_through_seq=run_read_point(store.list_records(conn, sample.grant.id)),
            data=data,
        )
        store.insert_records(conn, [record])
    return record.id


def _id(sample: SampleGrant, name: str) -> str:
    for x in [*sample.records, *sample.files, *sample.charges]:
        if x.id.rsplit("-", 1)[0] == name:
            return x.id
    raise KeyError(name)


SOON = APRIL_9 - timedelta(minutes=30)


# confirm_terms


def test_confirm_terms_confirms_the_files_waiting_terms(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    pack = golden_pack(tmp_path, [step(APRIL_9, "confirm_terms", file="extension_notice.txt")])
    resolved = _resolve(api, golden, pack)
    extension = _id(golden, "rec-period-extension")
    assert resolved == WriteRecord({"kind": "confirmation", "record_ids": [extension]})
    _act(api, golden, pack)
    assert _state(api, golden).is_effective(extension)
    # Done: nothing waits any more, so the same step now finds no target.
    assert _resolve(api, golden, pack) is None


def test_a_step_with_no_target_is_left_for_the_user(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    for action in (
        step(APRIL_9, "confirm_terms", file="invoice_1001.txt"),  # no terms in it
        step(APRIL_9, "answer_flag", line_id="L-1001", answer="supports"),  # no flag
        step(APRIL_9, "let_in_mail", file="sequencing_statement.eml"),  # nothing held
        step(
            APRIL_9,
            "decide_suggestion",
            suggestion="remainder",
            decision="accept",
            file="invoice_1001.txt",
        ),
        step(
            APRIL_9, "accept_reason", note="Fine.", check="period_of_performance", line_id="L-1001"
        ),
    ):
        pack = golden_pack(tmp_path / action["action"], [action])
        assert _resolve(api, golden, pack) is None, action


# decide_suggestion


def test_decide_suggestion_decides_the_agents_waiting_suggestion(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    bill = next(r for r in golden.records if r.id.startswith("rec-bill-inv-1001"))
    total = bill.data.total  # pyright: ignore[reportAttributeAccessIssue]
    remainder = Remainder(
        record_id=bill.id,
        other_award=CitedText(value="SYN-0000001", text="SYN-0000001", citation=total.citation),
        reason="The rest of the bill names another award.",
    )
    suggestion = _insert(api, golden, remainder, SOON)
    action = step(
        APRIL_9,
        "decide_suggestion",
        suggestion="remainder",
        decision="reject",
        file="invoice_1001.txt",
    )
    pack = golden_pack(tmp_path, [action])
    resolved = _resolve(api, golden, pack)
    assert resolved == WriteRecord(
        {"kind": "confirmation", "record_ids": [suggestion], "decision": "rejected"}
    )
    _act(api, golden, pack)
    assert _state(api, golden).decision(suggestion) == "rejected"


# answer_flag


def test_answer_flag_answers_the_agents_flag_on_the_line(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    flag = _insert(
        api,
        golden,
        Judgment(
            charge_id=_id(golden, "chg-l-1001"),
            question=Question.FLAG,
            text="Is a 50-count box of liners reasonable here?",
            answer=Answer.UNSURE,
            reasoning="The invoice doesn't say what the liners are for.",
        ),
        SOON,
    )
    pack = golden_pack(
        tmp_path, [step(APRIL_9, "answer_flag", line_id="L-1001", answer="supports")]
    )
    resolved = _resolve(api, golden, pack)
    assert isinstance(resolved, WriteRecord) and resolved.replaces_id == flag
    assert resolved.data["answer"] == "supports" and resolved.data["question"] == "flag"
    _act(api, golden, pack)
    answers = [
        r for r in _records(api, golden) if isinstance(r.data, Judgment) and r.replaces_id == flag
    ]
    assert len(answers) == 1 and answers[0].author == "user"


# enter_share


def test_enter_share_types_the_share_on_the_agents_link(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    action = step(
        APRIL_9,
        "enter_share",
        line_id="L-1001",
        file="invoice_1001.txt",
        share="1",
        out_of="2",
        basis="Half the liners are for this grant.",
    )
    pack = golden_pack(tmp_path, [action])
    resolved = _resolve(api, golden, pack)
    assert isinstance(resolved, WriteRecord)
    assert resolved.replaces_id == _id(golden, "rec-link-l-1001")
    assert resolved.data["amount_cents"] == 62000  # half of $1,240.00
    assert resolved.data["share"]["note"] == "Half the liners are for this grant."
    _act(api, golden, pack)
    [typed] = [r for r in _records(api, golden) if r.replaces_id == resolved.replaces_id]
    assert typed.author == "user"


# accept_reason


def test_accept_reason_accepts_the_checks_reason_on_the_line(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    # On Apr 9 the extension waits, so L-1002's date is outside the period in force.
    action = step(
        APRIL_9,
        "accept_reason",
        note="The extension covers it.",
        check="period_of_performance",
        line_id="L-1002",
    )
    pack = golden_pack(tmp_path, [action])
    resolved = _resolve(api, golden, pack)
    assert isinstance(resolved, WriteRecord)
    assert resolved.data["kind"] == "accepted_reason"
    assert resolved.data["charge_id"] == _id(golden, "chg-l-1002")
    assert resolved.data["reason"]["check"] == "period_of_performance"
    assert resolved.data["note"] == "The extension covers it."
    _act(api, golden, pack)
    assert any(r.kind.value == "accepted_reason" for r in _records(api, golden))


# let_in_mail


def test_let_in_mail_lets_the_held_message_in(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    from app.db.mail_sink import DbSink
    from app.ingest.incoming import IncomingFile, PendingHold

    pack = golden_pack(tmp_path, [step(APRIL_9, "let_in_mail", file="sequencing_statement.eml")])
    raw = pack.file_bytes("sequencing_statement.eml")
    held = IncomingFile(
        key="gmail:m-held",
        grant_id=golden.grant.id,
        workspace_id=golden.grant.workspace_id,
        source="gmail",
        name="sequencing_statement.eml",
        media_type="message/rfc822",
        data=raw,
        sender="billing@vendor.example",
        source_ref="m-held",
    )
    from app.contracts.mail import HoldReason

    DbSink(api.platform).hold(
        PendingHold(
            workspace_id=golden.grant.workspace_id,
            grant_id=golden.grant.id,
            sender="billing@vendor.example",
            from_header="Billing <billing@vendor.example>",
            gmail_message_id="m-held",
            subject="Usage statement",
            files=(held,),
            held_at=SOON,
            reason=HoldReason.UNKNOWN_SENDER,
        )
    )
    resolved = _resolve(api, golden, pack)
    assert isinstance(resolved, WriteRecord) and resolved.data["kind"] == "mail_action"
    assert resolved.data["action"] == "let_in"
    _act(api, golden, pack)
    assert any(
        isinstance(r.data, MailDecision) for r in _records(api, golden, APRIL_9 + timedelta(days=1))
    )


# sign_off and deliver_file


def test_sign_off_signs_with_the_scripts_note(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    pack = golden_pack(tmp_path, [step(APRIL_9, "sign_off", note="Reviewed; the extension waits.")])
    assert _resolve(api, golden, pack) == SignOff("Reviewed; the extension waits.")
    _act(api, golden, pack)
    assert any(
        r.kind.value == "sign_off" for r in _records(api, golden, APRIL_9 + timedelta(days=1))
    )


def test_deliver_file_resolves_only_when_the_file_isnt_there(
    api: Api, golden: SampleGrant, tmp_path: Path
) -> None:
    pack = golden_pack(tmp_path, [])
    from app.samples.pack import UserAction

    action = UserAction(at=APRIL_9, action="deliver_file", file="invoice_1001.txt")
    with transaction(api.platform.pool) as conn:
        assert resolve(api.platform, conn, golden.grant, pack, action, APRIL_9) is None
        before = UserAction(at=SOON, action="deliver_file", file="extension_notice.txt")
        early = APRIL_9 - timedelta(days=1)
        assert resolve(api.platform, conn, golden.grant, pack, before, early) == DeliverFile(
            "extension_notice.txt"
        )


# The loader's rules for the new kinds (ruling 59, as ruling 51's).


@pytest.mark.parametrize(
    ("action", "message"),
    [
        (step(APRIL_9, "accept_reason", check="budget"), "takes"),
        (step(APRIL_9, "accept_reason", note="  ", check="budget"), "isn't empty"),
        (step(APRIL_9, "accept_reason", note="Ok.", check="budget", problem=""), "isn't empty"),
        (
            step(
                APRIL_9,
                "accept_reason",
                note="Ok.",
                check="budget",
                line_id="L-1001",
                file="invoice_1001.txt",
            ),
            "a line_id, a file, or the grant",
        ),
        (step(APRIL_9, "sign_off"), "takes"),
        (step(APRIL_9, "sign_off", note=""), "isn't empty"),
        (step(APRIL_9, "let_in_mail", file="extension_notice.txt"), "isn't a Gmail file"),
        (step(APRIL_9, "let_in_mail"), "takes"),
        (
            step(
                datetime(2026, 2, 21, 17, 30, tzinfo=UTC),
                "let_in_mail",
                file="sequencing_statement.eml",
            ),
            "before",
        ),
    ],
)
def test_the_loader_refuses_a_bad_new_step(
    tmp_path: Path, action: dict[str, Any], message: str
) -> None:
    with pytest.raises(PackError, match=message):
        golden_pack(tmp_path, [action])


def test_the_loader_keeps_the_new_steps(tmp_path: Path) -> None:
    pack = golden_pack(
        tmp_path,
        [
            step(APRIL_9, "let_in_mail", file="sequencing_statement.eml"),
            step(
                APRIL_9,
                "accept_reason",
                note="Over, and fine.",
                check="budget",
                problem="over_limit",
            ),
            step(
                APRIL_9,
                "accept_reason",
                note="Ok.",
                check="period_of_performance",
                line_id="L-1002",
            ),
            step(APRIL_9, "sign_off", note="Signed with one item open."),
        ],
    )
    kinds = [(a.action, a.check, a.problem, a.line_id, a.note) for a in pack.actions]
    assert kinds == [
        ("let_in_mail", None, None, None, None),
        ("accept_reason", "budget", "over_limit", None, "Over, and fine."),
        ("accept_reason", "period_of_performance", None, "L-1002", "Ok."),
        ("sign_off", None, None, None, "Signed with one item open."),
    ]
