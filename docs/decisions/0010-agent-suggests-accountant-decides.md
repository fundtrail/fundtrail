# 0010. The agent suggests, and the accountant decides

**Date:** 2026-11-09 · **Status:** accepted. Amends [0009](0009-agent-judges-code-checks.md) and rule 1 of [0005](0005-four-trust-rules.md).

## Context

A design review before the build found places where [0009](0009-agent-judges-code-checks.md)'s limits could be bypassed or didn't reach:

- The agent couldn't replace the accountant's answer, but a second answer written beside it counted right away.
- The agent could clear its own flag by changing its answer, with no click.
- When code's check was wrong for a charge, nobody could say so. A cost before the start date stayed in Possible conflict even when an amendment allowed it, and the accountant couldn't clear it either.
- A charge with no evidence stayed off the problem list until 90 days before the end date. On a three-year grant that can be almost three years.
- Problems that aren't about one charge, such as the same invoice arriving twice, had nowhere to go.
- There was no place for the agent to make its case or for the accountant to ask it a question.

## Decision

- **What goes with the flow takes effect. What goes against it waits.** Anything the agent does that adds information or raises a concern takes effect right away: a comment, a link for evidence nobody has linked, a flag, a new checklist item, a first answer. Anything that would clear or weaken a problem, or change something already decided, is a suggestion that waits for the accountant: changing an answer, fixing a link, removing a checklist item, withdrawing its own flag, disputing a check.
- **One exception.** When the agent answered unsure and new evidence settles it, its new answer counts right away. New evidence means something new was linked to the charge, or a record the answer rested on was corrected or withdrawn. Code checks that.
- **The agent can suggest a new answer to the accountant's.** The suggestion waits, and the accountant's answer stays in force.
- **A bill and a charge have one link in force.** A second link beside the first waits like a fix.
- **The agent can dispute a check.** It names the check, its reasoning and a quote. The charge moves from Possible conflict to Needs a human, and the accountant accepts or rejects. Code hands the agent the failing checks on the charges in each run, so it doesn't have to remember them.
- **No repeats.** After a rejection, the agent can't raise the same suggestion or dispute again without new evidence.
- **Every charge can have a review thread,** and so can a record with a problem. The accountant can ask the agent a question there. A question goes ahead of the agent's queued work. An instruction to change something comes back as a suggestion with one click.
- **There's no resolve button.** A problem leaves the list when it fixes itself, when the accountant snoozes it until a date, or when the accountant accepts it with a note. A new problem ends a snooze early, and the closeout window ends every snooze. An acceptance covers the problem as it stood, so the charge comes back if the facts change.
- **Standing notes.** An acceptance can cover every charge on the grant with the same problem, ledger account and vendor, past and future. Code does the matching, and every other check still runs. A charge with no vendor only gets a one-off note.
- **Missing evidence is flagged sooner.** A charge goes on the problem list 60 days past the date its evidence was expected, or 90 days before the end date, whichever comes first. A missing approval is flagged right away. The 60 days is our own choice, fixed for every grant.
- **Records can have problems.** Code raises the clear-cut ones: a bill linked for more than its total, a bill nobody charged after 60 days, a term waiting for confirmation, confirmed terms that disagree, the exact same file twice. The agent can flag any record for anything else. A likely duplicate is flagged and held back from matching until the accountant decides.
- **The budget line is checked from two sides.** Code asks for an approval if either the ledger's account or the agent's budget line says one is needed. A disagreement goes to the accountant.
- **The evidence report shows decisions, not conversations.** Thread messages are kept in their own table and stay out of the report.

## Considered and set aside

- **Letting the agent override on its own for low-stakes checks.** That's where false clears come from. A person decides, and sees the agent's reasoning.
- **A resolve button.** The list could then say a charge is done while the checks say it isn't, with nothing recording why.
- **One thread per grant.** Talk about different charges gets mixed, and the review trail can't sit next to its charge.
- **Thread messages as records.** The report only needs decisions, so messages don't have to live in the evidence file.
- **Acting on an instruction right away.** A misread instruction would already be live. One extra click shows the change first.
- **A wider standing note:** the same account only, a scope the accountant chooses, or the agent applying it to near-matches. Account only would excuse every purchase on that account. The others were more than the problem needs.
- **A setting for the 60 days.** One number isn't worth a settings page.

## Consequences

- The contracts change: more of the agent's writes wait, and there are new records for accepted reasons, snoozes, disputes and flags on records, plus a thread messages table. The changes are listed in [contracts.md](../contracts.md#13-agreed-changes-not-yet-in-the-code) and need their own contract PR.
- Trust rule 1 becomes "the agent reads, links, answers and suggests."
- The five January charges an amendment allows come from different vendors, so one standing note doesn't cover them. Each is accepted on its own.
- Details that only change how a part is built are listed under "Not decided yet" in each doc. They're discussed with Alex before that part is built.
