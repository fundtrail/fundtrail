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
- **The screens.** The docs decide what the app does and what each screen holds. Grant's design system and clickable screens (pull request 11, under `frontend/design/`) are inspiration for the look and the general layout. Where they differ from the docs, the docs win. Nothing waits on the mockup.
- **Optional features** start only once the thin path works.

### What the first build includes

The first build includes everything except the optional features in [product.md](product.md#scope).

Areas that haven't been discussed yet aren't left out. A first version of each is built, and it's tracked as provisional in the list below. That way it's easy to override once it's discussed, and the first implementation isn't mistaken for a decision.

### Built first, discussed after

Whoever builds a provisional area records the choices they made for it in this list, in the same pull request. Each area also stays in its doc's "Not decided yet" table until it's discussed.

| Provisional area | Its open items are in | Choices made in the first version |
|---|---|---|
| Reversals and cost transfers, beyond their default checklist | [product.md](product.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | |
| A cost shared by two grants | [product.md](product.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | |
| The evidence report and the closeout sign-off | [product.md](product.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | |
| The clock | [product.md](product.md#not-decided-yet), [architecture.md](architecture.md#not-decided-yet) | |
| The seeded demo workspace and its data | [product.md](product.md#not-decided-yet), and below | |
| Gmail and Drive details | [architecture.md](architecture.md#not-decided-yet), [contracts.md](contracts.md#not-decided-yet) | |
| The eval's blind test and scoring | [eval.md](eval.md#not-decided-yet) | |

### Work in parallel

Parallelize as much as possible. Inside each stage, split the work across subagents or separate sessions wherever the pieces don't touch the same files. Shared files (contracts, migrations, docs) have one writer at a time.

- The three pieces of test material are independent of each other.
- The four areas on Alex's side (ingestion, the agent, quotes, the checks) live in separate folders.

## How we work

```
                    GitHub: grant-j-kim/fundtrail
     main + docs/ = the truth  ·  issues = tasks  ·  PRs = changes
            ▲                         ▲                        ▲
            │ read before each task   │ claim one              │ open one
            │                         │                        │
   Alex's lead session                          Grant's lead session
     ├ worker: W1 agent                           ├ worker: W4 platform
     ├ worker: W2 checks + rules                  ├ worker: W5 app screens
     └ worker: W3 ingestion, then eval            └ worker: W6 viewer + closeout

   one task = one issue = one worktree and branch = one PR
   Alex and Grant decide, review and merge. Agents never change direction.
```

- **Each person runs one lead session plus up to 3 workers at a time.** Review is the limit: one person can follow and merge about three streams. More agents than that bring more conflicts and unreviewed code, not more speed.
- **A lead session** picks the next issues and starts each worker with a short brief: the issue link and the docs to read. It reviews PRs with `/code-review`, and its human merges.
- **A worker** is a fresh session on one issue, in its own worktree, and finishes with a PR. The working rules are in [CLAUDE.md](../CLAUDE.md#working-rules).
- **Model: Opus 5.5 for every session.** Rework costs more than tokens here. Sonnet 5.5 is fine for narrow, fully specified tasks such as seed files, UI polish or test fixtures, when speed matters.
- **Status lives in GitHub issues,** not in this file, so parallel PRs don't collide on a shared status list. The one exception is the "Built first, discussed after" list above, which records choices, not progress.
- **The blind-test generator** is a separate claude.ai chat with no repo access (see [eval.md](eval.md)).

## Workstreams

The split follows one seam. Alex owns everything that turns files into records and records into statuses. Grant owns the platform and everything the user sees. The directories each workstream owns are in [CLAUDE.md](../CLAUDE.md#repo-map).

| # | Workstream | Owner |
|---|---|---|
| W1 | Agent: read with citations, write records and links, add to evidence checklists, answer the checks' questions, suggest fixes, dispute checks, reply in threads. Also quotes: find each quote in its file, highlight positions, page images for scans, the second look on photos | Alex |
| W2 | Checks, NSF rules, evidence checklists, link sums, the questions for the agent, buckets, the problem list, status history and status text | Alex |
| W3 | Ingestion: ledger file, Gmail, Drive, upload, file prep. Then eval and seed data | Alex |
| W4 | Platform: database, sign-in, workspaces, seeding, clock, API, background jobs on Procrastinate, thread messages, screen pings, deploys | Grant |
| W5 | App screens: sign-in, workspaces, grants, buckets, the problem list, charge detail with its checklist and thread, evidence cards, history, clock controls | Grant |
| W6 | Viewer with highlights, closeout view, PDF evidence report | Grant |
| Shared | Contracts, migrations, docs, `CLAUDE.md`, CI config | both |

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
Workstream: W#
May change: directories
Depends on: contracts or issues
Done when: a test passes, or a behavior you can see
Read first: docs sections
```

## Direction changes

Only Alex or Grant change direction.

1. Alex and Grant decide.
2. One PR adds a file to [decisions/](decisions/) and updates every doc and contract the decision touches. If a contract changes, the same PR updates its callers so main stays green, or the two owners agree on who follows up.
3. Affected issues get edited, closed or reopened, and labeled `changed`.
4. Running workers are told to stop, or to rebase and reread the decision.

A small correction inside one area doesn't need a decision file. The PR description is enough.

## Risks

- **Review bottleneck.** Workers are capped at three per person.
- **Contract churn.** Once the contract code is merged, later changes follow the process above.
- **Late integration.** The thin path comes before the parallel work, which forces integration early.
- **A first version mistaken for a decision.** Provisional areas are listed above, with the choices made for each.
- **Google test-mode tokens.** While the OAuth app is in Testing mode, Google refresh tokens expire after 7 days. Reconnect the demo account before a demo.
- **Cost.** Six Opus workers plus live eval runs. Keep an eye on the Anthropic console.

## Not decided yet

| Item | Who settles it |
|---|---|
| How to demo | product |
| Issues for the work in decisions 0010 to 0019. Review threads are core. | both leads |
| The demo data | product (Alex and Grant), built by W3 |
| The agent's exact actions and the wording of its prompts: a W1 task of its own, which can go to a worker. Using the eval to tune them is optional. See [architecture.md](architecture.md#the-agent). | builder (W1), discussed with Alex before building |
