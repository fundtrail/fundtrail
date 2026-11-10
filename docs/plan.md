# Plan

## Where things stand

As of November 9, 2026:

- **The docs describe the design through decisions [0010](decisions/0010-agent-suggests-accountant-decides.md), [0011](decisions/0011-evidence-checklist.md) and [0012](decisions/0012-checked-quotes-and-highlights.md).** They came out of a design review before the build.
- **The contract code still implements the design through [0009](decisions/0009-agent-judges-code-checks.md).** The changes it needs are listed in [contracts.md](contracts.md#13-agreed-changes-not-yet-in-the-code).
- **Nothing else is built.** The contracts are the only code in the repo. Everything else in the repo map is a target.
- **The dates below have passed.** Alex set the timeline aside to get the design right. The build order gets redone in step 3.

Still to discuss, in this order, because each feeds the next:

1. The tech stack and how each part is implemented
2. The structure of the codebase
3. The build plan
4. The UI flow

The contract PR comes after the UI flow, because what each screen gets from the server depends on it. Details that only change how a part is built are under "Not decided yet" in each doc, and they're discussed with Alex before that part is built.

## Milestones

| Milestone | When (PT) |
|---|---|
| Contracts frozen | Sun Nov 8, 10 AM |
| Walking skeleton deployed | Sun Nov 8, night |
| Feature freeze | Mon Nov 9, 9 PM |
| Internal submit | Tue Nov 10, 8 PM (10 PM is the buffer) |
| Hard deadline | Tue Nov 10, 11:59 PM |
| Live final, if selected | Thu Nov 19, San Francisco |

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
- **Status lives in GitHub issues,** not in this file, so parallel PRs don't collide on a shared status list.
- **The blind-test generator** is a separate claude.ai chat with no repo access (see [eval.md](eval.md)).

## Workstreams

The split follows one seam. Alex owns everything that turns files into records and records into statuses. Grant owns the platform and everything the user sees. The directories each workstream owns are in [CLAUDE.md](../CLAUDE.md#repo-map).

| # | Workstream | Owner |
|---|---|---|
| W1 | Agent: read with citations, write records and links, add to evidence checklists, answer the checks' questions, suggest fixes, dispute checks, reply in threads | Alex |
| W2 | Checks, National Science Foundation (NSF) rules, evidence checklists, link sums, the questions for the agent, buckets, the problem list, status history and status text | Alex |
| W3 | Ingestion: ledger file, Gmail, Drive, upload, file prep. Then eval and seed data | Alex |
| W4 | Platform: database, sign-in, workspaces, seeding, clock, API, background jobs, deploys | Grant |
| W5 | App screens: sign-in, workspaces, grants, buckets, the problem list, charge detail with its checklist and thread, evidence cards, history, clock controls | Grant |
| W6 | Viewer with highlights, closeout view, PDF evidence report | Grant |
| Shared | Contracts, migrations, docs, `CLAUDE.md`, CI config | both |

## Phases

| Phase | When | Done when |
|---|---|---|
| **0: Docs, contracts, skeleton** | Sat Nov 7 evening | Docs are on main. The contracts PR is open, covering everything in [contracts.md](contracts.md) plus the golden fixture. The repo layout, CI, and hello-world deploys run on Vercel and Railway against Supabase. Phase 1 issues exist. |
| **Contracts frozen** | Sun Nov 8, 10 AM | Alex and Grant approve the contracts PR together. |
| **1: Walking skeleton** | Sun Nov 8 | For one grant, one uploaded file goes through the agent, records and checks, and its bucket shows in the deployed app. |
| **2: Core features** | until Mon Nov 9, 9 PM | Everything on the core list in [product.md](product.md#scope) works end to end. Then feature freeze. |
| **3: Fix, eval, submit** | Tue Nov 10 | Bugs are fixed, the blind test has run, the README opens with the theme, the demo is decided, and the entry is submitted. |

Optional features start only once the walking skeleton works.

### Phase 0 tasks

| Task | Owner | Notes |
|---|---|---|
| Contracts: record models, tables, API stubs, checks interface, ledger columns, answer-key format, golden fixture | Alex (worker) | Touches only shared contract files. Both humans review. |
| Skeleton: repo layout from CLAUDE.md, move the Python project into `backend/`, Next.js app in `frontend/`, CI, hello-world deploys | Grant (worker) | Follows the layout in [CLAUDE.md](../CLAUDE.md#repo-map). Updates "Running things" in CLAUDE.md. |
| Setup only a person can do (below) | Alex and Grant | |
| Phase 1 issues, one per task, using the template below | both leads | |

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
- **Contract churn.** Contracts freeze Sunday morning. Later changes follow the process above.
- **Late integration.** Needing a walking skeleton by Sunday night forces integration early.
- **Google test-mode tokens.** While the OAuth app is in Testing mode, Google refresh tokens expire after 7 days. Reconnect the demo account before the Nov 19 final.
- **Cost.** Six Opus workers plus live eval runs. Keep an eye on the Anthropic console.

## Not decided yet

| Item | Who settles it |
|---|---|
| How to demo | product |
| Issues for the work in decisions 0010 to 0012, and the contract PR they need. Review threads are core. | both leads |
| The demo data | product (Alex and Grant), built by W3 |
| The agent's exact actions and prompts: a W1 task of its own, which can go to a worker. Using the eval to tune them is optional. See [architecture.md](architecture.md#the-agent). | builder (W1) |
