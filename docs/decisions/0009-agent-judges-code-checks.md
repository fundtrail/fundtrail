# 0009. Code checks the clear-cut rules, and the agent answers the rest

**Date:** 2026-11-09 · **Status:** accepted. Supersedes [0002](0002-agent-writes-records-code-decides.md). Amends rules 1 and 3 of [0005](0005-four-trust-rules.md).

## Context

[0002](0002-agent-writes-records-code-decides.md) had code decide every status, with the model only reading and linking. Working through real cases showed what that misses:

- Some rules can't be written as code. Berkeley's cost criteria ask whether a cost is necessary and reasonable and whether it belongs to the project. An espresso machine for a break room passes every date and amount check and is still unallowable.
- Award letters and amendments say things no fixed term type holds, such as a principal investigator on leave with an acting one named. Dropping those lets a charge clear when it shouldn't.
- Matching receipts to charges takes judgment. Invoices get paid in parts, one payment covers several invoices, and a cost is split across grants. A link to a whole file can't show which part of a receipt pays which charge.
- "Code does all math" was too strong. Matching needs simple math, such as adding up itemized lines.

## Decision

- **The agent is the app's intelligence. Code checks the clear-cut rules.** Code checks dates against the period in force, the link sums, whether evidence is linked, the approver's role and channel, budget room, and that every quote appears in its passage. When terms change, code reruns instantly, with no agent call.
- **Code asks, the agent answers.** For what code can't settle, code asks a question about a charge: Allowable, Covers, or Unusual term. The agent can also raise its own flag. Each answer is supports, contradicts or unsure, with the agent's reasoning and quotes, stored as a judgment record. Supports passes, contradicts is Possible conflict, and unsure is Needs a human. The agent can only clear a question code asked, so a skipped question never passes silently.
- **The accountant has the last word.** They answer what the agent was unsure about and can overrule any answer. Once they've answered, new evidence sends the question back to them, not to the agent.
- **Links tie a fact to a charge, with an amount and a part.** A receipt link says how much of the receipt the charge uses, and the part is the passage highlighted for that charge. A receipt's links add up to at most its total, and a charge's links add up to its amount. Over goes to a human. Under waits until 90 days before the end date. The agent can split a cost across charges, and there's no separate split record.
- **The agent suggests and the accountant approves changes.** The agent's first links count right away. Any fix it suggests to an existing link waits for the accountant, including a fix to one of the accountant's own links. It never changes the accountant's records on its own, and never their answers.
- **New record kinds:** `other_term` for anything else an award letter or amendment says, `note` for evidence that explains a charge, and `judgment` for answers. The agent decides which budget line a charge belongs to.
- **The agent works in a loop of actions.** It looks at anything on the grant with no filtering, and every write is checked as it happens. A run can't finish while code has an open question for it. The exact actions come with the prompts.
- **Trust rule 1** becomes "the agent reads, links and answers." **Trust rule 3** becomes "the agent may do simple math, and code re-checks every number it can."
## Considered and set aside

- **One broad question per charge** ("is anything wrong with this charge?"). It's simpler, but an overlooked concern passes silently. With a principal investigator on leave, the agent could answer supports without ever mentioning the leave. Code asks specific questions instead.
- **Links in a table of their own.** Judgments point at charges too, and they need the same database checks. One records table with real charge and record columns gives every kind those checks and keeps one mechanism for replacing, confirming and history.
- **A shortlist of candidate charges for matching.** Filtering could drop the charge that's needed. The agent looks through everything, and efficient sorting comes later.

## Consequences

- The contracts add links with amounts and parts, judgments, `other_term`, `note`, agent runs, and a write check that both the backend and the agent use. The split record is gone.
- The agent is no longer a fixed read-then-write pipeline. Where [0006](0006-stack.md) says "the read step", read "the agent's calls to the model". The contracts use "evidence report" and `GET /grants/{grant_id}/report`, which settles the naming note in [0008](0008-evidence-report-for-university-closeout.md).
- Open questions this decision leaves are listed under "Not decided yet" in [product.md](../product.md#not-decided-yet), [architecture.md](../architecture.md#not-decided-yet) and [contracts.md](../contracts.md#not-decided-yet).
- Status text still comes from code. The agent's reasoning is shown next to it, labeled as the agent's.
- The eval scores the agent's links and answers as well as its records, and counts false clears on their own: an answer of supports where the right answer is contradicts or unsure.
- The checks (W2) and the agent (W1) build against [contracts.md](../contracts.md). The agent's prompts have to balance firm rules against flexibility, since models follow rules too literally. Code enforces only a few hard limits.
