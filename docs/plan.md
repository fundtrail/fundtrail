# Plan

## The order of work

There are no dates. The work goes in this order ([decisions/0019](decisions/0019-build-order.md)). The two columns of a stage run at the same time.

| Stage | One side | The other side |
|---|---|---|
| 1 | The remaining design | The skeleton: the folders, an empty backend and frontend that deploy, the database, and automatic checks on every pull request (PR) |
| 2 | The contracts as code, for records, checks and the agent side, written from [contracts.md](contracts.md) | The test material: the sample grant redone to follow a real award letter, a first set of eval cases, and the National Science Foundation (NSF) rulebook |
| 3 | One thin path end to end: a file goes in, the agent reads it, the checks run, and a status shows on a screen | |
| 4 | Everything else, in parallel | |
| 5 | The full seed data and the blind test | |

- **The skeleton** follows the layout in [CLAUDE.md](../CLAUDE.md#repo-map) and fills in its "Running things" section.
- **The screens.** The docs decide what the app does and what each screen holds. Grant's design system and clickable screens (pull request 11) are inspiration for the look and the general layout. Where they differ from the docs, the docs win. Nothing waits on the mockup.
- **Optional features** start only once the thin path works.

### What the first build includes

The first build includes everything except the optional features in [product.md](product.md#scope).

Areas that haven't been discussed yet aren't left out. Before one is built, its design is worked through from first principles and written down as a decision file in [decisions/](decisions/) whose status line says "Provisional: not yet reviewed by Alex". Building follows that file. A provisional file can be overridden when it's reviewed, and a first implementation is never a decision.

### Provisional areas

Each area gets a link to its decision file here once the file is written. Whoever builds an area doesn't edit this list. A builder who has to make a further choice inside a provisional area says so in the pull request description. Each area also stays in its doc's "Not decided yet" table until it's reviewed.

| Provisional area | Its open items are in | Provisional decision file |
|---|---|---|
| Reversals and cost transfers, beyond their default checklist | [product.md](product.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | Not written yet |
| A cost shared by two grants | [product.md](product.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | Not written yet |
| The evidence report and the closeout sign-off | [product.md](product.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | Not written yet |
| The clock | [product.md](product.md#not-decided-yet), [architecture.md](architecture.md#not-decided-yet) | Not written yet |
| The seeded demo workspace and its data | [product.md](product.md#not-decided-yet), and below | Not written yet |
| Gmail and Drive details | [architecture.md](architecture.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | Not written yet |
| The eval's blind test and scoring | [eval.md](eval.md#not-decided-yet) | Not written yet |

### Work in parallel

Parallelize as much as possible. Inside each stage, split the work across separate agents wherever the pieces don't touch the same files. Shared files (contracts, migrations, and the continuous integration (CI) config) have one writer at a time.

- The three pieces of test material are independent of each other.
- Ingestion, the agent, quotes and the checks live in separate folders.

## How we work

```
   one task = one issue = one worktree and branch = one PR
```

- **One task is one issue.** Whoever takes it works in one area, in their own worktree, and finishes with a PR. The working rules are in [CLAUDE.md](../CLAUDE.md#working-rules).
- **Review before merge.** A PR merges to main once someone other than its author has reviewed it against the docs and the tests pass.
- **The design discussion continues during the build.** A new decision goes into the docs first, then to whoever is building the part it affects. A change to work that's already merged becomes a new issue.
- **Status lives in GitHub issues,** not in this file, so parallel PRs don't collide on a shared status list.
- **The blind-test generator** is a separate claude.ai chat with no repo access (see [eval.md](eval.md)).

## Areas

The work is split into areas of the repo. The directories each area owns are in [CLAUDE.md](../CLAUDE.md#repo-map).

| # | Area |
|---|---|
| W1 | Agent: read with citations, write records and links, add to evidence checklists, answer the checks' questions, suggest fixes, dispute checks, reply in threads. Also quotes: find each quote in its file, highlight positions, page images for scans, the second look on photos |
| W2 | Checks, NSF rules, evidence checklists, link sums, the questions for the agent, buckets, the problem list, status history and status text |
| W3 | Ingestion: ledger file, Gmail, Drive, upload, file prep. Then eval and seed data |
| W4 | Platform: database, sign-in, workspaces, seeding, clock, API (application programming interface), background jobs on Procrastinate, thread messages, screen pings, deploys |
| W5 | App screens: sign-in, workspaces, grants, buckets, the problem list, charge detail with its checklist and thread, evidence cards, history, clock controls |
| W6 | Viewer with highlights, closeout view, PDF evidence report |
| Shared | Contracts, migrations, docs, `CLAUDE.md`, CI config |

### Setup only a person can do

- [ ] A Supabase project with Google sign-in turned on
- [ ] A Google Cloud project: an OAuth client, the Gmail and Drive APIs, and the demo Gmail account
- [ ] Vercel and Railway projects linked to the GitHub repo
- [ ] The Anthropic API key and other secrets, set in Vercel, Railway and each person's local `.env`
- [ ] Branch protection on main: PRs required and CI must pass
- [ ] Alex has write access to `grant-j-kim/fundtrail`
- [ ] Labels: `W1` to `W6`, `contract`, `in progress`, `changed`

## Issue template

```
Goal: one or two sentences.
Area: W#
May change: directories
Depends on: contracts or issues
Done when: a test passes, or a behavior you can see
Read first: docs sections
```

## Direction changes

Only Alex changes direction.

1. Alex decides.
2. A file is added to [decisions/](decisions/), and every doc the decision touches is updated. If a contract changes, the code that uses it is updated in the same PR so main stays green, or an issue is opened for the follow-up.
3. The affected issues are edited, closed or reopened and labeled `changed`. A change to work that's already merged becomes a new issue.
4. Whoever is at work on an affected issue is told to stop, or to rebase and reread the decision.

A small correction inside one area doesn't need a decision file. The PR description is enough.

## Risks

- **Review bottleneck.** The build can only run as fast as reviews and merges keep up.
- **Contract churn.** Once the contract code is merged, later changes follow the process above.
- **Late integration.** The thin path comes before the parallel work, which forces integration early.
- **A provisional decision mistaken for a reviewed one.** Its status line says "Provisional: not yet reviewed by Alex", and the provisional areas are listed above.
- **Google test-mode tokens.** While the OAuth app is in Testing mode, Google refresh tokens expire after 7 days. Reconnect the demo account before a demo.
- **Cost.** Many agents at once plus live eval runs. Keep an eye on the Anthropic console.

## Not decided yet

| Item | Who settles it |
|---|---|
| How to demo | product |
| Issues for the work in decisions 0010 to 0019. Review threads are core. | whoever runs the build |
| The demo data | product, built by W3 |
| The agent's exact actions and the wording of its prompts: a W1 task of its own. Using the eval to tune them is optional. See [architecture.md](architecture.md#the-agent). | builder (W1), discussed with Alex before building |
