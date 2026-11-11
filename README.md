# FundTrail

**Automate the Old Way.** Proving that a research grant's spending followed the rules still means piecing together spreadsheets, email chains and receipts by hand at closeout. FundTrail keeps a running evidence file for every grant instead. An agent reads evidence as it arrives, writes records that cite the exact source text, matches them to charges, and answers the judgment calls, such as whether a cost is reasonable for the project. Code rechecks every clear-cut rule and sorts each charge into Evidence complete, Possible conflict, Missing evidence or Needs a human. When the grant ends, the review is already done and the evidence report is ready to attach to the university's closeout step (Berkeley's Award Closeout Certification is the first example). A person makes every final call.

Built by Alex ([azhao8](https://github.com/azhao8)) and Grant ([grant-j-kim](https://github.com/grant-j-kim)) for the BBS x Ramp Hackathon, "Build it" track.

**All demo data is synthetic.** No person, award number or email address in it is real. Award numbers start with `SYN-`, and email addresses use the `.example` domain.

## How it works

- **The agent judges.** It reads the award letter and the evidence (email, Google Drive files, uploads), and writes records that quote the exact passage they rest on. It links evidence to charges and answers what code can't settle: is this cost necessary and reasonable, is it for this project, does this approval cover this charge.
- **Code checks.** The clear-cut rules (dates, the evidence checklist, approvals, the budget, reversals) are a pure function rerun whenever a record changes, with no agent call.
- **Citations are checked against the file.** Code finds every quote in its source file. A quote that can't be placed sends the charge to a person.
- **A person makes every final call.** Anything the agent does that would clear a problem is a suggestion that waits for the accountant, who can accept, reject or overrule it. The accountant confirms the grant's terms before any check uses them, and signs off at closeout.

## What runs today

On main:

- **Sign-in** with Google (Continue with Google).
- **Workspace:** the grant list, and a sidebar with Grants (each with its problem count), Add a grant and Held mail.
- **Add a grant:** upload the award letter, or open a sample from a dropdown.
- **Terms:** the terms the agent read from the letter, each with Confirm, Reject or Type the right value.
- **Ledger upload** (CSV, comma-separated values, or Excel), reporting the lines added and skipped.
- **Evidence files**, each with its facts and the charges it pays for, plus confirming values the agent read.
- **The viewer** highlights the cited passage in its file and says how it was found: Exact passage, Close match on the page, or Couldn't be placed in the file.
- **The charge page:** its bucket and every reason, the evidence checklist, the bills covering it, the agent's answers and the status history. Actions: Accept, Accept with a note, Accept the same way, Snooze, Add a checklist item.
- **A record's thread:** the agent's suggestions (Accept or Reject) and a box to ask the agent a question.
- **Held mail** from unknown senders: Let in or Dismiss.
- **Gmail and Google Drive** checked for new evidence every minute.
- **The timeline panel** on a sample grant: Next event, Next highlight, go to a date (with Skip the human steps), and Start over.
- **Closeout:** Berkeley's closeout steps, what's still open, the evidence report draft (a PDF, Portable Document Format, file), Sign off, Withdraw the sign-off, and What changed since sign-off.

## Running it locally

The commands live in [CLAUDE.md, "Running things"](CLAUDE.md#running-things). In short, you need uv with Python 3.12, Node 24 with pnpm, and Docker, then:

- **Backend** (FastAPI), from `backend/`: `uv sync`, then `uv run fastapi dev` (port 8000). Lint, type check and tests run with ruff, pyright and pytest.
- **Frontend** (Next.js), from `frontend/`: `pnpm install`, then `pnpm dev` (port 3000). Also `pnpm lint`, `pnpm typecheck`, `pnpm build`.
- **Database**, from the repo root: `npx supabase start`, `npx supabase db reset`, `npx supabase stop`.

Copy `.env.example` to `.env` and add keys as each part needs them. Sign-in currently needs a Google sign-in set up in Supabase. Without one, set `NEXT_PUBLIC_FAKE=1` for fake mode: a synthetic demo user and synthetic data, with a banner on every page. Three fixes for local setup are landing: cross-origin settings (pull request, or PR, 220), email sign-in (PR 221) and creating the first workspace (PR 222).

## Architecture

- **Frontend:** Next.js 16 (`frontend/`).
- **API (application programming interface):** FastAPI (`backend/app/api/`).
- **Agent:** a LangGraph graph calling Claude as `claude-opus-5-5` (`backend/app/agent/`).
- **Quotes:** finds each cited passage in its file, using pypdfium2 for PDFs (`backend/app/quotes/`).
- **Checks:** a pure function that sorts each charge into one of the four buckets, rerun on every record change (`backend/app/checks/`).
- **Ingest:** the ledger file, Gmail, Google Drive and uploads (`backend/app/ingest/`).
- **Jobs:** Procrastinate on Postgres, one lock per grant (`backend/app/db/jobs.py`).
- **Clock:** one clock per grant, real time for a real grant and simulated time for a sample (`backend/app/db/clock.py`).
- **Supabase:** Postgres, sign-in, file storage, and realtime pings that refresh the screen (`supabase/`).
- **Evidence report:** a PDF built with ReportLab (`backend/app/packet/`).
- **Samples:** the timeline and its player (`backend/app/samples/`), with two sample grants in `data/samples/`.

## Not built yet

- **Sample content.** The two sample grants on main are placeholders. Their real content and highlights are in open PR 218.
- **The prerun sample**, with the agent's work done ahead of time. It shows as unavailable.
- **Receipt photos** aren't confirmed automatically. They go to a person.
- **Word (.docx) files and scanned PDFs** aren't read yet.
- **The eval** has cases and answer keys in `eval/cases/` but no runner that scores them.
- **Hosting.** There's no deploy config in the repo. Run it locally.

## For contributors and agents

Start with [CLAUDE.md](CLAUDE.md), then [docs/](docs/): [product](docs/product.md), [architecture](docs/architecture.md), [contracts](docs/contracts.md), [domain](docs/domain.md), [eval](docs/eval.md), [plan](docs/plan.md) and [decisions](docs/decisions/).
