# 0022. The evidence report is frozen at sign-off

**Date:** 2026-11-10 · **Status:** accepted, except as noted here. Reviewed by Alex on 2026-11-10 and kept as written: sign-off is allowed with problems still open when the accountant writes a note, a signed report stays as signed and a later change shows without reopening it, and nothing blocks sign-off except the agent still working on the grant. The report's layout is accepted too. Still the builder's choice: how the PDF is made. Not decided: withdrawing a sign-off. Amended by [0028](0028-one-clock-per-grant.md) (dates on the report come from the grant's clock), [0029](0029-workspace-members-and-one-access-check.md) (nothing assumes a workspace has one person, and the preparer is whoever signs off) and [0027](0027-sample-grants.md) (a reset is starting one sample grant over, not resetting a workspace).

## Context

The evidence report is a Portable Document Format (PDF) file per grant that shows why each charge was allowed. It goes next to the university's own ledger report at closeout, and the funder never receives it ([product.md](../product.md)). What goes into it is decided: decisions, not conversations ([0010](0010-agent-suggests-accountant-decides.md)). Its layout, the sign-off, and what a later change does were left open.

Two readers decide the shape.

- **The preparer's supervisor,** now. At Berkeley the supervisor approves the Award Closeout Certification in the university's system, and submitting it indicates the principal investigator's approval of the final expenses. The supervisor needs the totals and whatever is still open.
- **An auditor,** years later. They pick a charge and ask for everything behind it.

One fact decides the rest: FundTrail works statuses out fresh each time, from the records and the rules. If a rule changes next year, a report made again from the same records could come out different. A signed report can't be allowed to change.

## Decision

- **The order serves both readers:** what's open first, then everything.
  1. Summary: the grant, the terms in force, spending against the award's limit and against each budget line, the count in each bucket, and the accepted and reversed charges counted on their own. It states the ledger total FundTrail holds and the latest posting date, so it can be matched to the university's ledger report.
  2. Open at sign-off: every charge that isn't Evidence complete, accepted or fully reversed, with its reasons, every open problem on the grant, a record or a file, and any mail still held from unknown senders ([0025](0025-gmail-and-drive.md)).
  3. Decisions: the list [0010](0010-agent-suggests-accountant-decides.md) already sets.
  4. Every charge, one row each. A charge that was corrected is shown together with its corrections and the net ([0020](0020-reversals-and-cost-transfers.md)).
  5. A section per charge: each checklist item and what fills it, with the quoted passage, its file and its page. Each check's result is labeled as code's, and each of the agent's answers as the agent's, with the rule it used.
  6. Sources: every file cited, with its checksum, so a file can later be shown to be the same one.
  7. The sign-off.
- **The accountant signs off, and anyone else signs on paper.** A workspace has one person for now. The supervisor's approval happens in the university's own system, so the report prints blank "Reviewed by" lines and stores nothing about them.
- **Nothing blocks a sign-off except a run in progress.** The accountant has the last word. Signing off with anything still open requires a note. While an agent run for the grant is running or queued, a sign-off is refused with that reason, and the accountant tries again when the agent is done. Otherwise the report would be signed mid-change.
- **Signing off stores the PDF.** The stored file is what was signed, with its checksum on the sign-off. It's never made again.
- **A later change doesn't undo a sign-off. It shows.** If a charge's bucket, an accepted or reversed status, the problem list or a total changes afterwards, the grant shows "changed since sign-off" with what changed, and the accountant can sign off again. The earlier signed report stays on file. A comment or a link that changes no status doesn't count.
- **A sign-off can be withdrawn** with a retraction, like any decision.
- **"Ready for closeout"** counts charges that are Evidence complete, accepted or fully reversed. A snoozed charge isn't ready. A partly corrected charge is an ordinary charge, judged on its net amount.
- **The report route gives the current draft.** A signed report is fetched through its sign-off.
- **Dates on the report are the workspace's clock** ([0023](0023-the-clock.md)).
- **The original files aren't inside the PDF.** They're listed in Sources. A zip of them stays optional.
- **The closeout view** shows the university's closeout steps in order, what's still open, the report, and the sign-off. It shows the dates that follow from the end date. A deadline that depends on the university's own calendar, such as the close of a month's ledger, isn't worked out. Berkeley's steps are the first set.

## Considered and set aside

- **Making the report again on request, with no stored copy.** It could differ after a rule change.
- **Reopening the sign-off on any change.** The agent writes all the time, so the grant would rarely stay signed.
- **Requiring every charge to be complete or accepted before signing.** It could make an honest sign-off impossible.
- **A second user who reviews.** More users and roles are later.
- **A shorter report with detail only for open charges.** It's weaker for an audit.

## Consequences

- The contracts add the stored report and its checksum to the sign-off, and a way to tell what changed since. Names and fields are open.
- How the PDF is produced is the builder's choice, discussed before building: free or very cheap, production-ready, light to set up, and checked against its current documentation.
- Whether sections use the university's cost criteria as labels stays open in [product.md](../product.md#not-decided-yet).
- A workspace reset deletes its records and stored reports. How long a real workspace keeps them isn't decided.

## For review

The calls most likely to change: that nothing blocks a sign-off, what counts as a change worth showing, and the order of the sections.
