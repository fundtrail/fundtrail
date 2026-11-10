# 0016. Default checklists hang on groups of accounts

**Date:** 2026-11-10 · **Status:** accepted. Amends [0011](0011-evidence-checklist.md).

## Context

[0011](0011-evidence-checklist.md) gave each ledger account a default evidence checklist, for Berkeley's accounts first, but the defaults were never written. Berkeley's public account list has about 359 expense accounts. A list for each one is more than the idea needs.

The budget line is also checked from two sides: the ledger's account against the budget line the agent picked ([0010](0010-agent-suggests-accountant-decides.md)). Nothing said how an account maps to a budget line of a National Science Foundation (NSF) award.

## Decision

- **A default hangs on a group of accounts,** not on each account. There are about a dozen groups, each with one list. Code keeps a small table that says which account codes belong to which group, taken from Berkeley's public account list. The starting groups: salaries, benefits, tuition and fee remission, travel, supplies, equipment, participant support, subawards, consultants and services, printing, and internal recharges.
- **A default holds only what every charge in the group needs.** Differences inside a group, such as a flight and a hotel, are left to the agent's own items. An account in no group gets no default, as before.
- **The list for each group is a starting point.** It's in [domain.md](../domain.md#default-checklists-by-account-group).
- **The effort report follows Berkeley's timing.** Berkeley certifies effort twice a year, within 120 days of the period's end. The report for January to June is expected by late October, and the checklist item carries that date.
- **A budget line is one of NSF's standard budget categories,** so it needs no category of its own. Only the ledger's account is translated: each account group carries its NSF category, in the same table as its default list, and code compares that with the budget line the agent picked.

## Considered and set aside

- **A default for each account.** Berkeley has about 359 expense accounts.
- **Giving each budget line a category too,** confirmed by the accountant, and comparing category with category. Real award notices print the budget in NSF's standard categories already ([0017](0017-grant-terms-from-award-notices.md)), so the budget line is the category.

## Consequences

- The example in [product.md](../product.md#the-evidence-checklist) changes: an effort report covers six months, not a quarter.
- The table of account codes, groups and NSF categories still has to be written and checked against Berkeley's account list. The demo ledger's accounts have to be in it.
- Some default items were checked on Berkeley's own pages and some come from general practice. [domain.md](../domain.md#default-checklists-by-account-group) says which.
- Berkeley is replacing its effort system, so the timing is re-checked before building. Whether Berkeley has moved its equipment and subaward thresholds isn't verified.
- The table covers Berkeley's accounts for now.
