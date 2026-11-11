"""An answer that names a rule carries what the rule says, in plain words (issue 303)."""

from __future__ import annotations

import uuid

from app.agent.rulebook import load_rulebook, rule_entry
from app.api.views import _rule_view  # pyright: ignore[reportPrivateUsage]
from app.contracts.records import Judgment
from app.db import store
from app.db.pool import transaction
from tests.api.conftest import Api
from tests.api.test_screens import _get, _id, _sample  # pyright: ignore[reportPrivateUsage]


def test_every_rule_has_its_words_and_every_source_parses():
    rulebook = load_rulebook()
    for rule_id in rulebook.ids:
        entry = rule_entry(rulebook, rule_id)
        assert entry is not None and entry.text and entry.kind, rule_id
        for label, url in entry.sources:
            assert label and url.startswith("https://") and url.count("(") == url.count(")")
    assert rule_entry(rulebook, "NSF-NO-SUCH-RULE") is None


def test_the_alcohol_rule_reads_in_plain_words_with_its_sources():
    view = _rule_view("NSF", "NSF-NEVER-ALCOHOL")
    assert view is not None
    assert (view.title, view.text) == ("Not allowed", "Alcoholic beverages are not allowed.")
    assert [s.label for s in view.sources] == [
        "2 CFR 200.423",
        "NSF PAPPG 24-1, Chapter II.D.2.f(xiii)(c)",
    ]
    assert _rule_view("NSF", None) is None
    assert _rule_view("NSF", "NSF-NO-SUCH-RULE") is None


def test_the_charge_page_sends_the_rule_an_answer_names(api: Api) -> None:
    sample = _sample(api)
    charge_id = _id(sample, "chg-l-1001")
    [old] = [
        r for r in sample.records if isinstance(r.data, Judgment) and r.data.charge_id == charge_id
    ]
    assert isinstance(old.data, Judgment)
    contradicts = old.model_copy(
        update={
            "id": str(uuid.uuid4()),
            "replaces_id": old.id,
            "stored_seq": None,
            "data": old.data.model_copy(
                update={"answer": "contradicts", "rule": "NSF-NEVER-ALCOHOL"}
            ),
        }
    )
    with transaction(api.platform.pool) as conn:
        store.insert_records(conn, [contradicts])
    [answer] = _get(api, f"/charges/{charge_id}")["answers"]
    assert answer["judgment"]["data"]["rule"] == "NSF-NEVER-ALCOHOL"
    assert answer["rule"]["text"] == "Alcoholic beverages are not allowed."
    assert answer["rule"]["sources"][0]["url"].startswith("https://www.ecfr.gov/")
