# 0021. A shared cost: a part of a bill needs a cited basis, and the rest is the accountant's to explain

**Date:** 2026-11-10 · **Status:** accepted. Reviewed by Alex on 2026-11-10 and kept as written: a link for part of a bill needs a cited basis or the charge is Needs a human, where the basis is a share, code checks the arithmetic to within one cent, where no document gives the basis, the accountant enters it, and the agent's suggestion that the rest belongs to another award waits for the accountant, while a remainder nobody has explained is flagged after 60 days.

## Context

One bill can pay for work on two grants. The federal rule is 2 CFR 200.405: a cost that benefits several projects is split by the benefit each gets, or on any reasonable documented basis when the proportions can't be worked out. The exact wording should be checked against the regulation before anyone relies on it.

What's decided already: a split is one bill linked to several charges, each link with its amount and the part of the bill it covers, and for now each grant is isolated ([0009](0009-agent-judges-code-checks.md)). So a shared invoice arrives on both grants, and each grant holds its own copy.

That leaves three gaps.

- **Who states this grant's share, and from what.** A $10,000 sequencing invoice covers 96 samples, and 56 are this grant's. The ledger charges this grant $5,833.33. Nothing says what counts as proof of the 56.
- **A way to clear a charge by accident.** If the agent links exactly $5,833.33 of the $10,000 invoice with nothing behind the number, the amounts add up and the charge shows as Evidence complete. The match proves nothing: the agent copied the amount from the charge.
- **A false alarm.** On this grant's copy of the invoice, $4,166.67 was never charged. After 60 days code raises "a bill with money nobody charged", though the other grant paid it.

## Decision

- **A link for part of a bill has to rest on a cited passage.** When a link covers less than the bill's total, and other charges on this grant don't account for the rest, the link's amount needs something cited behind it: a line on the bill itself that states that part, or a document that gives the basis, such as an email saying "56 of the 96 samples are for this grant". Without one, the charge is in Needs a human, whatever the sums say. Code checks this, because it's clear-cut.
- **Where the basis is a share, code checks the arithmetic.** The share's two numbers and the bill's total are all cited values: 56, 96 and $10,000. The worked-out amount has to match the charge to within one cent, since a three-way split can't divide evenly.
- **Where no document gives the basis, the accountant enters the share and the basis.** A value the accountant types counts as confirmed.
- **The agent can suggest that the rest belongs to another award. It can't settle it.** The passage that gives the basis usually names the other award. The agent suggests recording that the remainder belongs there, citing the passage, and the suggestion waits for the accountant ([0010](0010-agent-suggests-accountant-decides.md)). The suggestion is about the bill, so it waits on the bill and doesn't change the charge's bucket. Once accepted, the remainder isn't "money nobody charged".
- **A remainder nobody has explained is still flagged** on the bill after 60 days, as today. The accountant can accept it with a note.

## Considered and set aside

- **Letting matching amounts be enough.** That is the accidental clear described above.
- **Letting the agent record the remainder on its own.** It would stop a problem from being raised, and what clears a problem waits for the accountant.
- **Turning the 60-day flag off for any bill linked in part.** It would hide a real uncharged amount.
- **Letting grants see each other,** so one grant's remainder can be matched to the other's charge. Sharing between grants is out for now.
- **Requiring proportions whenever they can be measured.** That takes judgment about the science. The agent's Allowable question already covers a basis that looks unreasonable.

## Consequences

- The contracts add a way to record that part of a bill belongs to another award, and the check gains the rule for a part with no cited basis. Names and fields are open.
- FundTrail can't check that the other grant really charged its part, or that the grants' shares add up to the bill. That needs grants that share evidence.
- A third grant sharing the same bill works the same way: each grant states its own share.

## For review

- Whether a part of a bill with no cited basis should be Needs a human, as here, or should only be flagged by the agent.
- How close the worked-out share has to be to the charge. One cent is the suggestion.
