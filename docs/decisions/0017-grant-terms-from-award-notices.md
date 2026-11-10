# 0017. Grant terms follow real award notices, and checks use only confirmed terms

**Date:** 2026-11-10 · **Status:** accepted

## Context

The accountant confirms a grant's terms before any check uses them. The docs left open what a charge shows meanwhile, both for a new grant and between an amendment's arrival and its confirmation.

The design had also never been checked against a real National Science Foundation (NSF) award notice. Reading real ones showed:

- The budget is printed in the notice, in NSF's standard categories. Materials and Supplies is a sub-line inside Other Direct Costs, not a category beside it. The sample grant had them side by side.
- Every notice is an amendment with a number and a type. A funding amendment prints a budget for that increment only, beside the total obligated to date. So a grant's budget can be the sum of several notices.
- The notice names its program solicitation, and a solicitation can set limits of its own, such as a stipend cap.

The facts are in [domain.md](../domain.md#what-an-nsf-award-notice-contains).

## Decision

- **Checks use only confirmed terms.** Where an older confirmed term exists, it stays in force. Where none exists, the charge is in Needs a human.
  - On a new grant, each charge is in Needs a human with a reason such as "the grant's dates aren't confirmed yet". Checks that need no terms still run, such as the checklist and the amounts. The problem list shows the waiting terms as one item, and confirming them clears all of those charges at once.
  - On an existing grant, the old term stays in force. A charge dated after the end date stays in Possible conflict until the accountant confirms the extension.
- **A wrong term.** The accountant rejects it and fixes it one of two ways: they type the right value, which counts as confirmed because they typed it, or they tell the agent in the term's thread where to look, and the agent's new reading waits for confirmation like any other.
- **A term the agent missed.** Code flags a grant that has no confirmed dates or no budget, since no grant can lack those. The accountant adds the missing term by hand or asks the agent to read the letter again.
- **The agent doesn't wait for confirmation.** It reads evidence, links it and builds checklists while the terms wait. Anything that rests on an unconfirmed term stays in Needs a human until the terms are confirmed.
- **A notice that adds money adds to the award's limit.** The agent reads the notice's type, the amount it adds and the running total, each with its quote. Code checks that the earlier confirmed total plus the amount added equals the notice's running total. If it doesn't, the grant is flagged, since a notice is missing or a number was misread. A gap in the amendment numbers is flagged the same way. The accountant confirms the term as usual.
- **A program solicitation added to a grant as a source updates its terms** the same way the award letter and an amendment do, confirmed by the accountant. There's no new kind of record for it.
- **The sample grant follows the real budget layout.** Materials and Supplies is a sub-line of Other Direct Costs.

## Considered and set aside

- **Code catching other missed terms.** It can't, because it doesn't know what the letter should contain.
- **Anything specific to solicitations,** for now: adding up a cap over several charges, such as twelve monthly payments that pass a yearly cap together, and noticing that the award letter names a solicitation that isn't on file. Left for later.

## Consequences

- The open rows about a charge's bucket before its terms are confirmed are gone from [product.md](../product.md#not-decided-yet) and [contracts.md](../contracts.md#not-decided-yet).
- The known weak spot: when the agent misses an approval rule, its check never runs.
- The contracts add a term for a funding notice's amounts and problems on the grant itself. Their names and fields aren't settled. Neither is how a funding notice's own budget lines combine with the lines already confirmed, or how a budget line records its category.
- The sample grant in [contracts.md](../contracts.md#15-the-sample-grant) changes: its budget is laid out like a real notice's, and the second charge is assigned to the sub-line Other.
- No new-project notice to a research university was read, only one to a community college and amendments to a research university.
