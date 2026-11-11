# 0030. A benefit charge is recalculated from its rate and its salary

**Date:** 2026-11-10 · **Status:** accepted. Amends [0011](0011-evidence-checklist.md) and [0016](0016-default-checklists-by-account-group.md). The items under "First versions" were agreed to be built and judged running, and may change.

## Context

Every salary line on a grant has a benefit line beside it, and a benefit line has no bill of its own. The benefits account group's default checklist asks for the "Benefit rate" ([0016](0016-default-checklists-by-account-group.md)), and nothing could fill it.

What the sources say, with quotes and links in [domain.md](../domain.md#benefit-charges):

- Berkeley charges most benefits by a composite benefit rate for each employee group. The rates are agreed with the Department of Health and Human Services (DHHS) one fiscal year at a time, in a rate agreement.
- Berkeley has one benefit ledger account for each rate group, so the account tells the group.
- A benefit posts to the same department and fund as its salary.
- Auditors check benefits by recalculating them on sampled salary.

Two scenarios show the gap.

- January's Staff salary on the grant is $6,000, and the Staff rate for that fiscal year is 44.0%. A $2,640 benefit line posts beside it. Nothing ever fills its "Benefit rate" item, so after 60 days it's on the problem list as missing evidence, though nothing is wrong with it.
- The same month, a $2,940 benefit line posts instead. A rate on file that nobody multiplies out doesn't show the $300 difference.

## Decision

- **The rate agreement is a document on the grant.** The agent reads its rates as terms, one for each employee group and fiscal year, each tied to its passage. The accountant confirms them once, like any term.
- **The ledger account tells the rate group.**
- **Code recalculates, month by month and group by group.** The expected benefit is the confirmed rate for the fiscal year the salary falls in, times that month's salary of that group on the grant. A match fills the benefit charge's "Benefit rate" item, citing the rate term and the salary lines. A mismatch is Needs a human, and the reason shows what was expected against what was charged.
- **A benefit charge follows its salary.** It isn't Evidence complete until its salary lines are.
- **The agent flags what code can't see,** such as benefits charged on a stipend, or a rate from the wrong year.
- **This is the general mechanism, and a first version for real grants.** Left for later: pay left out of the calculation, such as vacation; tuition and fee remission, which is charged at actual cost; leave assessments; and benefits after a salary is moved by a cost transfer.
- **In the sample grants,** benefit lines sit beside salary lines and clear with them. They aren't a highlight ([0027](0027-sample-grants.md)).

### First versions

- **A confirmed rate stays in force** until a later confirmed one replaces it, as with any term.
- **A benefit charge waiting on its salary** shows Missing evidence, with the reason that it waits on its salary lines. On the problem list it's shown with its salary line's row, not as a row of its own.

## Considered and set aside

- **A benefit charge simply following its salary, with no check.** Nothing would catch a wrong rate.
- **A payroll document for every benefit charge.** Auditors recalculate, and no such document arrives for each charge.

## Consequences

- [0016](0016-default-checklists-by-account-group.md)'s "Benefit rate" item is filled by code's recalculation, not by a link.
- [0011](0011-evidence-checklist.md) has the agent write the math for an amount from a rate, and code re-check it. For a benefit charge, code does the math itself, from the confirmed rate and the salary lines.
- Which salary accounts belong to which rate group at Berkeley isn't verified ([domain.md](../domain.md#not-decided-yet)).
- The contracts add a benefit rate's employee group and the dates it's in effect, a checklist item code fills by recalculating, the expected amount on a mismatch, and how a waiting benefit charge shows with its salary line's row. Names and fields are open ([contracts.md](../contracts.md#not-decided-yet)).

## For review

The first versions above:

- a confirmed rate staying in force until a later confirmed one replaces it
- a waiting benefit charge showing Missing evidence, and showing with its salary line's row on the problem list
