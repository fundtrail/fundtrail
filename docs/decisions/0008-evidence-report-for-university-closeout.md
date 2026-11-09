# 0008. The evidence report fits the university's own closeout step

**Date:** 2026-11-08 · **Status:** accepted

## Context

The docs described a "closeout packet" with an accountant's sign-off, as if that were an existing step. Research against the National Science Foundation's (NSF's) policy guide, the federal rules and several universities' procedures showed otherwise (sources in [domain.md](../domain.md#sources)):

- NSF never receives charge-level evidence. It gets one final payment amount in ACM$ (Award Cash Management Service) and two research reports, all due 120 days after the end date.
- The federal rules do require supporting documentation for every charge, kept for 3 years and handed to auditors on request. Today it's scattered across systems and inboxes, and nobody gathers it in one place.
- Universities do run a real internal closeout review. At Berkeley, the research administrator files an Award Closeout Certification two months after the end date, with a ledger report and supporting documents, and a supervisor approves it. Stanford, WashU and UC Davis have similar steps with different forms, systems and deadlines.
- No source describes a per-grant evidence packet. The ledger report Berkeley requires shows only what was spent, not why each charge was allowed.

## Decision

- The "closeout packet" becomes the **evidence report**: the proof behind every charge, attached to the university's existing closeout step. FundTrail doesn't replace any university step and files nothing.
- **Berkeley is the first template and the demo example.** The checks follow the shared federal and NSF rules. Only the report's format and labels follow the university.
- The user, still called "the accountant," is whoever prepares a grant's closeout. At Berkeley, that's the department's research administrator.
- The sign-off stays, mirroring the preparer and the reviewer in the university's own step.
- Two optional features are added: drafted explanations for charges moved off the grant, and an audit export for the charges an auditor picks.

## Consequences

- [product.md](../product.md#closeout), [domain.md](../domain.md#closeout), [architecture.md](../architecture.md#trust-rules), [plan.md](../plan.md), [CLAUDE.md](../../CLAUDE.md) and the README now say "evidence report" instead of "packet." Where [0001](0001-running-evidence-file.md) and [0005](0005-four-trust-rules.md) say "packet," read "evidence report."
- The pitch describes FundTrail as doing the review universities already have to do, not as producing a document NSF requires.
- W6 builds the evidence report in Berkeley's terms. The `app/packet/` directory keeps its name.
- The open contracts PR (`alex/contracts`) still says "packet" in three places: the `sign_off` record's description, its docstring in `records.py`, and the `GET /grants/{grant_id}/packet` route. The names can stay. The descriptions get updated in that PR or right after it merges.
- New open items are listed in product.md: the report's name and layout, whether checks use the university's cost criteria as labels, and how drafted explanations are written.
