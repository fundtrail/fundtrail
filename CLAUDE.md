# FundTrail

FundTrail keeps a running evidence file for every research grant. Charges come from the university's ledger. An agent reads the evidence (email, Google Drive files, uploads) and writes records that cite the exact passages. Code reruns every check whenever a record changes and puts each charge in a bucket. When the grant ends, the review the university has to do is already done, and the evidence report is ready to attach to the university's closeout step (Berkeley's Award Closeout Certification is the first example).

Built by Alex (azhao8) and Grant (grant-j-kim) for the BBS x Ramp Hackathon, "Build it" track. Theme: "Automate the Old Way". Feature freeze is Mon Nov 9, 9 PM PT, and submission is Tue Nov 10 (see [docs/plan.md](docs/plan.md)).

## Read first

| If you're working on | Read |
|---|---|
| Anything | This file, then your workstream in [docs/plan.md](docs/plan.md) |
| What the user sees, and the scope | [docs/product.md](docs/product.md) |
| How the parts fit, the stack, the clock, the trust rules | [docs/architecture.md](docs/architecture.md) |
| Records, tables, the API, file formats | [docs/contracts.md](docs/contracts.md) |
| NSF rules, grant terms, closeout | [docs/domain.md](docs/domain.md) |
| The eval | [docs/eval.md](docs/eval.md) |
| Why something is the way it is | [docs/decisions/](docs/decisions/) |

**If the docs don't say it, it isn't decided.** Each doc ends with a "Not decided yet" list, and each item there names who settles it:

- **contract:** Alex and Grant together, before parallel work depends on it.
- **product:** Alex and Grant, when the work reaches it.
- **builder:** whoever builds that part decides it inside their own area and notes it in the PR.

If something crosses areas or changes what the user sees, ask in your issue. Don't guess.

## Repo map

```
backend/          FastAPI app (Python, uv)
  app/contracts/  Pydantic record models, golden fixture   shared
  app/agent/      LangGraph: read and write                W1 Alex
  app/checks/     rules, buckets, status text              W2 Alex
  app/ingest/     ledger, Gmail, Drive, upload             W3 Alex
  app/api/        routes                                   W4 Grant
  app/db/         database access, clock, jobs             W4 Grant
  app/packet/     PDF evidence report                      W6 Grant
  tests/
frontend/         Next.js app                              W5 Grant (viewer: W6)
supabase/         migrations (shared), config, seed        W4 Grant
eval/             cases, answer keys, runner               W3 Alex
data/             synthetic seed packs                     W3 Alex
spikes/           throwaway experiments
docs/, CLAUDE.md  docs                                     shared
```

This is the target layout. The skeleton task creates it, so until then only `spikes/`, `data/demo/` and the docs exist.

## Working rules

1. Pull main, then read this file and the doc for your area before you start.
2. One task is one GitHub issue. Claim it by assigning your human and adding the `in progress` label. If it's already claimed, take another.
3. Work in your own worktree, on a branch named `<alex|grant>/<issue>-<slug>`.
4. Change files only in your workstream's directories. If you need something changed outside them, comment on the issue or open one for that owner. Don't edit it yourself.
5. Shared files change only in a PR that both Alex and Grant approve: contracts, migrations, docs, this file, CI config.
6. Keep PRs small and merge them often. Rebase on main before opening one. Main stays green: CI runs lint, type checks and tests on every PR.
7. Build against the contracts and the golden fixture, never against another workstream's unfinished code.
8. Never make a product decision or change direction. If you think the plan is wrong, say so in the issue and stop.
9. Before opening a PR, check `docs/decisions/` for new files and follow them.
10. Write commit messages and PR descriptions that say what changed and why.

## Project rules

- All demo data is synthetic (see [data/demo/SYNTHETIC.md](data/demo/SYNTHETIC.md)). Award numbers start with `SYN-`, and email addresses use the `.example` domain.
- Never commit `.env` or any key, and never print credentials.
- No invented statistics, no savings claims, and no percentages in the README or the pitch.
- The README and the pitch open with the theme.
- Prose rules: be direct and concise, spell out acronyms on first use, and don't use em dashes.
- The app calls Claude as `claude-opus-5-5`.

## Running things

Right now only the citation spike runs:

```bash
cp .env.example .env   # then add ANTHROPIC_API_KEY
uv run --env-file .env python spikes/citation_test.py
```

The skeleton task replaces this section with the backend, frontend and test commands.
