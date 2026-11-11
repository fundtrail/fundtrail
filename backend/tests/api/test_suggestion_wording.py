"""Issue 304: a waiting suggestion carries the server's wording of what accepting it
changes, in a record's own thread as on a charge's page."""

from __future__ import annotations

import uuid

from app.contracts.records import Record
from app.db import store
from app.db.pool import transaction
from tests.api.conftest import Api
from tests.api.test_screens import _get, _id, _sample  # pyright: ignore[reportPrivateUsage]


def test_a_bills_thread_titles_the_remainder_suggestion_as_the_server_words_it(
    api: Api,
) -> None:
    sample = _sample(api)
    bill = _id(sample, "rec-bill-inv-1001")
    [template] = [r for r in sample.records if r.id == bill]
    remainder = Record.model_validate(
        {
            "id": str(uuid.uuid4()),
            "workspace_id": template.workspace_id,
            "grant_id": template.grant_id,
            "author": "agent",
            "written_at": template.written_at,
            "read_through_seq": template.read_through_seq,
            "data": {
                "kind": "remainder",
                "record_id": bill,
                "other_award": {"value": "SYN-2300999", "uncited": True},
                "reason": "The invoice splits the order with award SYN-2300999.",
            },
        }
    )
    with transaction(api.platform.pool) as conn:
        store.insert_records(conn, [remainder])
    entries = _get(api, f"/records/{bill}/thread")["entries"]
    [entry] = [e for e in entries if e["kind"] == "record" and e["record"]["id"] == remainder.id]
    assert entry["state"] == "waiting"
    assert entry["change"]["title"].startswith("Put the rest of the bill in invoice_1001.txt")
    assert entry["change"]["title"].endswith("on award SYN-2300999")
    others = [e for e in entries if e["kind"] == "record" and e["record"]["id"] != remainder.id]
    assert all(e["change"] is None for e in others)
