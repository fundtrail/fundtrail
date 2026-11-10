"""Netting a charge with the lines that correct it (decision 0020).

A ledger never edits a line: a reversal or a cost transfer is a new line. A line
that takes money off the grant nets against the line it corrects, and what counts
for the corrected line is its net amount. A correction can itself be corrected,
and the netting follows the chain: when a reversal is reversed, the original
counts in full again. A line that adds money to the grant never nets into a line
that also added money: it's a real cost here and stands on its own.

Which line a line corrects: the line its ledger row names, when that line is on
the grant; otherwise the line a current `correction` record names (the agent's
waits for the accountant, so netting starts only once they accept it). Ledger line
IDs are unique per grant, not per workspace, so a line ID is only ever looked up
among the charge's own grant's charges.
"""

from collections.abc import Sequence

from .base import Cents, Id, Model
from .charges import Charge
from .records import Correction
from .rules import RecordState


class NetAmount(Model):
    """One charge's net amount.

    Nets aren't additive: a line that nets into another (`nets_into` is set) is counted
    inside that line's net, so the nets of a grant's charges don't add up to its ledger.
    """

    charge_id: Id
    net_cents: Cents  # the charge's amount with the lines netted into it
    corrections: tuple[Id, ...] = ()  # the charges netted into this one, in ledger line order
    reversed: bool = False  # fully corrected: something was netted and the net is zero
    nets_into: Id | None = None  # the charge this line nets into, if it nets into one


def corrected_line(charge: Charge, charges: Sequence[Charge], state: RecordState) -> Charge | None:
    """The line on the charge's grant that `charge` corrects, or None when none is known yet."""
    on_grant = {c.ledger_line_id: c for c in charges if c.grant_id == charge.grant_id}
    if charge.original_line_id is not None:
        by_ledger = on_grant.get(charge.original_line_id)
        if by_ledger is not None:
            return by_ledger
    suggested: Charge | None = None
    for r in state.current():
        data = r.data
        if isinstance(data, Correction) and data.charge_id == charge.id:
            named = on_grant.get(data.corrects_line_id)
            if named is not None:
                suggested = named
    if suggested is not None and suggested.id == charge.id:
        return None
    return suggested


def _nets_into(line: Charge, target: Charge) -> bool:
    """A line nets into the line it corrects when it moves that line's amount toward zero."""
    return line.id != target.id and line.amount_cents * target.amount_cents < 0


def net_amounts(charges: Sequence[Charge], state: RecordState) -> dict[Id, NetAmount]:
    """Every charge's net amount, with the charges netted into it."""
    charges = sorted(charges, key=lambda c: (c.ledger_line_id, c.id))
    into: dict[Id, list[Charge]] = {}
    target_of: dict[Id, Id] = {}
    for c in charges:
        target = corrected_line(c, charges, state)
        if target is not None and _nets_into(c, target):
            into.setdefault(target.id, []).append(c)
            target_of[c.id] = target.id

    nets: dict[Id, int] = {}
    visiting: set[Id] = set()

    def net(c: Charge) -> int:
        if c.id in nets:
            return nets[c.id]
        if c.id in visiting:  # a loop in the ledger's naming: stop following it
            return c.amount_cents
        visiting.add(c.id)
        total = c.amount_cents + sum(net(x) for x in into.get(c.id, []))
        visiting.discard(c.id)
        nets[c.id] = total
        return total

    result: dict[Id, NetAmount] = {}
    for c in charges:
        netted = sorted(into.get(c.id, []), key=lambda x: (x.ledger_line_id, x.id))
        amount = net(c)
        result[c.id] = NetAmount(
            charge_id=c.id,
            net_cents=amount,
            corrections=tuple(x.id for x in netted),
            reversed=bool(netted) and amount == 0,
            nets_into=target_of.get(c.id),
        )
    return result
