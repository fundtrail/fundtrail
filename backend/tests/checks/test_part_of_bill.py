"""Decision 0021 (#79): a link for part of a bill rests on a cited basis, the share's arithmetic,
the basis values confirmed, and remainder records.

The example: a $10,000 sequencing invoice covers 96 samples, 56 of them this grant's,
and the ledger charges this grant $5,833.33.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.contracts.checks import Bucket

from .grant_builder import Grant, at, cited, failing, families

TOTAL = 1_000_000
PART = 583_333
WHEN = at(2024, 3, 1)


def _shared(g: Grant, t: dict[str, str], charge: str = "c1", amount: int = PART) -> str:
    """The charge, the whole invoice on file, assigned and answered; no link yet."""
    g.charge(charge, date(2024, 3, 1), amount)
    g.assign(charge, t["ms"], WHEN)
    if not any(f.id == "f-inv" for f in g.files):
        g.file("f-inv", WHEN)
        return g.bill(TOTAL, "f-inv", WHEN)
    return next(r.id for r in g.records if r.kind == "bill")


def _link(g: Grant, bill: str, charge: str, amount: int, **basis: Any) -> str:
    data: dict[str, Any] = {
        "kind": "link",
        "record_id": bill,
        "charge_id": charge,
        "amount_cents": amount,
        "part": cited(0, "x", "f-inv")["citation"],
        "default_item": "bill",
        **basis,
    }
    link = g.agent(data, WHEN)
    g.answer(charge, "supports", WHEN, rests_on=[bill])
    return link


def _share(share: int, out_of: int, total: int = TOTAL, match: str = "exact") -> dict[str, Any]:
    return {
        "share": {
            "share": cited(Decimal(share), f"{share} of the", "f-email", match),
            "out_of": cited(Decimal(out_of), f"{out_of} samples", "f-email", match),
            "total": cited(total, f"${total // 100:,}.00", "f-inv", match),
        }
    }


def test_a_part_of_a_bill_with_nothing_cited_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    bill = _shared(g, t)
    link = _link(g, bill, "c1", PART)
    status = g.status("c1", at(2024, 3, 2))
    assert families(status) == {("checklist", f"part_without_basis:{link}")}
    assert status.bucket == Bucket.NEEDS_HUMAN  # though the amounts add up


def test_a_share_with_its_cited_basis_that_works_out_passes() -> None:
    g = Grant()
    t = g.standard_terms()
    g.file("f-email", WHEN)
    bill = _shared(g, t)
    _link(g, bill, "c1", PART, **_share(56, 96))  # $10,000 x 56 / 96 = $5,833.33
    status = g.status("c1", at(2024, 3, 2))
    assert failing(status) == []


def test_a_share_that_doesnt_work_out_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    g.file("f-email", WHEN)
    bill = _shared(g, t)
    link = _link(g, bill, "c1", PART, **_share(50, 96))
    status = g.status("c1", at(2024, 3, 2))
    assert ("checklist", f"share_mismatch:{link}") in families(status)
    reason = next(r for r in status.reasons if r.problem.startswith("share_mismatch"))
    assert "is $5,208.33, not the $5,833.33 linked" in reason.text


def test_a_share_of_a_different_total_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    g.file("f-email", WHEN)
    bill = _shared(g, t)
    # $5,000 x 56 / 96 = $2,916.67 works out, but $5,000 isn't the bill's $10,000.
    link = _link(g, bill, "c1", 291_667, **_share(56, 96, total=500_000))
    status = g.status("c1", at(2024, 3, 2))
    assert ("checklist", f"share_total_mismatch:{link}") in families(status)


def test_a_part_the_bill_states_passes_and_a_different_one_doesnt() -> None:
    g = Grant()
    t = g.standard_terms()
    bill = _shared(g, t)
    _link(g, bill, "c1", PART, stated_amount=cited(PART, "$5,833.33", "f-inv"))
    assert failing(g.status("c1", at(2024, 3, 2))) == []

    g2 = Grant()
    t2 = g2.standard_terms()
    bill2 = _shared(g2, t2)
    link = _link(g2, bill2, "c1", PART, stated_amount=cited(500_000, "$5,000.00", "f-inv"))
    assert ("checklist", f"part_mismatch:{link}") in families(g2.status("c1", at(2024, 3, 2)))


def test_a_stated_part_cited_from_another_file_is_needs_a_human() -> None:
    """The review's case: $5,833.33 copied into an email isn't a line on the bill."""
    g = Grant()
    t = g.standard_terms()
    g.file("f-email", WHEN)
    bill = _shared(g, t)
    link = _link(g, bill, "c1", PART, stated_amount=cited(PART, "$5,833.33", "f-email"))
    status = g.status("c1", at(2024, 3, 2))
    assert families(status) == {("checklist", f"part_not_on_bill:{link}")}
    assert status.bucket == Bucket.NEEDS_HUMAN


def test_a_stated_part_the_accountant_typed_counts() -> None:
    """A typed value has no citation and counts as confirmed (contracts.md section 1)."""
    g = Grant()
    t = g.standard_terms()
    bill = _shared(g, t)
    data = {
        "kind": "link",
        "record_id": bill,
        "charge_id": "c1",
        "amount_cents": PART,
        "default_item": "bill",
        "stated_amount": {"value": PART},  # typed: no citation
    }
    g.user(data, WHEN)
    g.answer("c1", "supports", WHEN, rests_on=[bill])
    assert failing(g.status("c1", at(2024, 3, 2))) == []


def test_a_bill_split_across_this_grants_charges_needs_no_basis() -> None:
    g = Grant()
    t = g.standard_terms()
    bill = _shared(g, t, "c1", 600_000)
    _shared(g, t, "c2", 400_000)
    _link(g, bill, "c1", 600_000)
    _link(g, bill, "c2", 400_000)
    out = g.run(at(2024, 3, 2))
    for status in out.charges:
        assert failing(status) == [], status.charge_id


def test_a_share_the_agent_couldnt_confirm_in_its_file_is_needs_a_human() -> None:
    g = Grant()
    t = g.standard_terms()
    g.file("f-email", WHEN)
    bill = _shared(g, t)
    link = _link(g, bill, "c1", PART, **_share(56, 96, match="not_found"))
    status = g.status("c1", at(2024, 3, 2))
    assert families(status) == {("values_confirmed", "unconfirmed")}
    assert link in next(r for r in failing(status)).record_ids


def _remainder(g: Grant, bill: str, author: str) -> str:
    data = {
        "kind": "remainder",
        "record_id": bill,
        "other_award": cited("SYN-2400999", file_id="f-email"),
        "reason": "The email says the other 40 samples are for SYN-2400999.",
    }
    return g.add(author, data, at(2024, 3, 5))


def test_a_remainder_the_accountant_accepted_keeps_the_rest_from_being_unused() -> None:
    g = Grant()
    t = g.standard_terms()
    g.file("f-email", WHEN)
    bill = _shared(g, t)
    _link(g, bill, "c1", PART, **_share(56, 96))
    later = at(2024, 6, 1)  # past 60 days
    assert any(r.record_id == bill for r in g.run(later).records)  # "unused"

    suggestion = _remainder(g, bill, "agent")  # the agent's waits
    out = g.run(later)
    assert any(r.record_id == bill for r in out.records)
    assert not any(r.problem.startswith("waiting:") for r in failing(out.charges[0]))

    g.confirm(suggestion, when=at(2024, 3, 6))
    assert all(r.record_id != bill for r in g.run(later).records)
