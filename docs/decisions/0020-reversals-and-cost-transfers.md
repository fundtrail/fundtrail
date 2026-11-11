# 0020. A line that takes money off the grant is read together with the line it corrects

**Date:** 2026-11-10 · **Status:** accepted. Reviewed by Alex on 2026-11-10 and kept as written: a line that takes money off the grant is read together with the line it names, a fully corrected charge shows Reversed and leaves the problem list with no action, when the ledger names no line, code doesn't guess and the agent's suggestion waits, and a line that adds money to the grant stands on its own with its group's default plus the two correction items. Berkeley's 120-day limit on cost transfers stays unchecked, because the university's own policies come in only through the default checklists for now. Amends [0010](0010-agent-suggests-accountant-decides.md) and [0016](0016-default-checklists-by-account-group.md).

## Context

A ledger never edits a line. It corrects itself with new lines: a reversal cancels a charge, and a cost transfer moves one to or from another fund. Moving a charge off the grant is how most problems get fixed at closeout, so this has to work.

What's decided already: a correcting line has a negative amount when money leaves the grant, it can name the line it corrects, and its default checklist is the line it corrects plus a written justification ([0011](0011-evidence-checklist.md), [0016](0016-default-checklists-by-account-group.md)). What isn't: what happens to the original charge.

Two scenarios show the gap.

- A $2,180 charge is in Possible conflict because it's dated after the grant ended. The accountant moves it off the grant, and a -$2,180 line arrives naming it. Nothing connects the two, so the original stays in Possible conflict forever, though the grant no longer pays for it.
- A $400 charge is followed by a -$150 line naming it. The $400 charge still expects $400 of bills.

## Decision

- **A line that takes money off the grant nets against the line it names.** What counts for the named line is its net amount. A correction can itself be corrected, and the netting follows the chain: when a reversal is reversed, the original counts in full again.
- **Fully corrected (the net is zero).** The original shows as Reversed, leaves the problem list and stays visible. It keeps the bucket the checks give it, so nothing is hidden, and it's counted as reversed, on its own. Its sums are no longer checked. This amends [0010](0010-agent-suggests-accountant-decides.md), which lists three ways a problem leaves the list: a full reversal is a fourth, because the grant no longer pays for the charge.
- **Partly corrected.** The charge stays an ordinary charge, judged on its net amount. Its checklist amounts have to add up to the net: for the example, a $400 invoice and a $150 credit note.
- **The correcting line is a charge of its own,** with its two items. A line that takes money off needs no amounts to add up. Its two items are filled or they aren't.
  - "The line it corrects" is filled in one of two ways: the ledger names a line that's on this grant, or a passage in the transfer's paperwork names the original. The second way is the only one for a line on another fund, which this grant can't see. Until one of the two happens, the item is unfilled and nothing is netted. Code doesn't try to tell a line that's late from a line that's elsewhere.
  - The written justification is a document on the grant, linked like any other evidence.
- **When the ledger names no line, code doesn't guess.** A line that takes money off the grant still gets the two correction items, as [0011](0011-evidence-checklist.md) decided, and "the line it corrects" is simply unfilled. The agent may say which line it believes is corrected, with its reason. That changes how another charge is judged, so it's a suggestion that waits for the accountant ([0010](0010-agent-suggests-accountant-decides.md)). Netting starts only if the accountant accepts it.
- **A line that adds money to the grant never nets into another line.** It's a real cost here, and it stands on its own: its checklist is its account group's default plus the two correction items. That covers a transfer onto the grant from another fund, and a charge moved between two accounts on the same grant, where the old line is reversed and a new line carries the cost. This amends [0016](0016-default-checklists-by-account-group.md), which gave every correcting line the two items in place of its account's default.
- **A bill linked to a fully reversed charge is free again.** Its links to that charge no longer use up its total, so it can be linked to the line that now carries the cost. It isn't flagged as money nobody charged, because the ledger shows what happened to the money.
- **Signs.** Amounts add up with their signs. A credit note has a negative total, and the links to it add up to no more than that total in size.

## Considered and set aside

- **Leaving the original as it is.** It keeps a false problem on a charge the grant no longer pays for.
- **Deleting or hiding the pair.** The ledger shows both lines, and an auditor will ask about them.
- **Letting the agent's match take effect at once.** It can clear a problem, and what clears a problem waits.
- **Netting a line that adds money.** The cost would be counted on the old line and on the new one.

## Consequences

- The contracts add a way to show a charge as reversed and to net a charge with its corrections. Names and fields are open.
- A transfer in from another fund can't be checked against its original, because each grant is isolated for now.
- Whether a justification answers the university's own questions isn't judged. Any written justification fills the item.
- The evidence report shows a corrected charge together with its corrections and the net ([0022](0022-evidence-report-and-sign-off.md)).

## For review

- Whether a reversed charge keeps its bucket or gets a state of its own.
- Whether a full reversal should take a charge off the problem list with no action from the accountant.
- Berkeley asks for cost transfers within 120 days of the close of the month the original charge posted. Nothing checks that here. Whether it should be checked is Alex's to decide ([domain.md](../domain.md#not-decided-yet)).
