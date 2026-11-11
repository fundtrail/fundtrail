# FundTrail

**Automate the Old Way.** Proving that a research grant's spending followed the rules still means piecing together spreadsheets, email chains and receipts by hand at closeout. FundTrail keeps a running evidence file for every grant instead. An agent reads evidence as it arrives, writes records that cite the exact source text, matches them to charges, and answers the judgment calls, such as whether a cost is reasonable for the project. Code rechecks every clear-cut rule and sorts each charge into Evidence complete, Possible conflict, Missing evidence or Needs a human. When the grant ends, the review is already done and the evidence report is ready to attach to the university's closeout step (Berkeley's Award Closeout Certification is the first example). A person makes every final call.

Built by Alex ([azhao8](https://github.com/azhao8)) and Grant ([grant-j-kim](https://github.com/grant-j-kim)) for the BBS x Ramp Hackathon, "Build it" track.

**All demo data is synthetic.** No person, award number or email address in it is real, and no document in it was issued by any agency or institution. Award numbers start with `SYN-`, and email addresses use the `.example` domain.

## How it works

- **The agent judges.** It reads the award letter and the evidence (email, Google Drive files, uploads), and writes records that quote the exact passage they rest on. It links evidence to charges and answers the questions code asks but can't settle: is this cost necessary and reasonable and for this project, does this approval cover this charge, does this term change anything for this charge.
- **Code checks.** The clear-cut rules (dates, the evidence checklist, approvals, the budget, confirmed values, reversals) and the recalculation of benefit charges are a pure function. It reruns whenever a record changes, with no agent call.
- **Quotes are checked against the file.** Code finds each quote in its file: the exact characters in text and email, and the passage on its page in a PDF (Portable Document Format), by exact match first and then a close one. On photos and scanned pages the agent boxes each value, and a second look that sees only the boxed area has to read the same value. A value that can't be placed or read the same stays unconfirmed, and any charge resting on it goes to Needs a human until the accountant confirms or corrects it.
- **A person makes every final call.** Anything the agent does that would clear or weaken a problem, or change something already decided, is a suggestion that waits for the accountant, who can accept or reject it. The one exception: when the agent answered unsure and new evidence settles it, its new answer counts right away. The accountant can overrule any answer, confirms the grant's terms before any check uses them, and signs off at closeout.

## What runs today

On main:

- **Sign-in** with Google ("Continue with Google"; built, not yet tried with a real Google project), or for local development a sign-in link sent by email ("Email me a link").
- **Workspace:** a sidebar with All grants, Held mail and Add a grant. Inside a grant, the sidebar lists Overview, Problem list (with its count), Charges, Evidence, Grant terms, Ledger and Closeout.
- **Add a grant:** upload the award letter for your own grant, or choose a sample grant and open it.
- **Grant terms:** the terms the agent read from the letter, each with Confirm, Reject or Type the right value.
- **Ledger upload** of a CSV (comma-separated values) or Excel file. It reports the lines added and the lines already on file, and lists each rejected row with the reason.
- **The grant overview:** how many things need you, the first few of them, and Open the problem list. It also shows the charges ready for closeout by bucket, the amount charged against the award's limit, the next closeout date, the budget, and links to Grant terms, Reusable notes and All charges.
- **The problem list** on its own page, with a filter for each bucket and the selected item shown beside the list. A benefit charge waiting on its salary line is listed under that line's row.
- **All charges** in one table, each with its date, ledger account, budget line, amount and bucket.
- **The charge page:** an evidence trail from the ledger line through the bills and evidence covering it, what's missing, the agent's answers and every failing reason. Below that come the evidence checklist and the status history, with the review thread docked beside or under them. Actions: Accept with a note, Accept the same way, Answer or Overrule a question, Add item to the checklist, Snooze and Reopen.
- **Review threads** on a charge or a record: the agent's suggestions, each with Accept or Reject, and a box to ask the agent a question.
- **Benefit charges** are recalculated from the confirmed benefit rate and the salary beside them. A match fills the charge's benefit rate item, and a mismatch goes to Needs a human.
- **Evidence:** each file with its facts and the charges it pays for, plus a page to confirm or correct the values the agent read (Confirm as read or Type the right value). The viewer highlights the cited passage in its file and says how it was found: Exact passage, Close match on the page, or Couldn't be placed in the file.
- **Held mail** from unknown senders: Let in or Dismiss.
- **The timeline** on a sample grant: Next event, Next highlight (it does the steps before the highlight for you and leaves the highlight's own step to you), Go to a date, Skip the human steps (for Next event and Go to a date), and Start over. A move that can't happen says why, and the panel says when the agent is still catching up on what arrived.
- **Closeout:** Berkeley's closeout steps, what's still open, every expense with its evidence and history, the evidence report draft as a PDF, Sign off, Withdraw the sign-off, and What changed since sign-off. When you can't sign off yet, the reason shows next to the button.

## Running it locally

You need uv with Python 3.12, Node 24 with pnpm, Docker (Colima works on macOS) and an Anthropic API key for the agent. Locally you sign in with an emailed link, so you don't need to set up Google.

1. **Start the database.** With Docker running, run `npx supabase start` from the repo root. It sets up the tables and prints the local URLs (web addresses) and keys. `npx supabase stop` stops it, and `npx supabase db reset` rebuilds it.
2. **Fill in the backend's settings.** Copy `.env.example` to `.env` at the repo root, then set:
   - `ANTHROPIC_API_KEY`: the agent needs it.
   - `DATABASE_URL`: the database URL that `supabase start` printed (port 54322).
   - `SUPABASE_URL`: `http://127.0.0.1:54321`.
   - `SUPABASE_SERVICE_ROLE_KEY`: the secret key that `supabase start` printed.
   - `FUNDTRAIL_DEV_EMAIL_SIGNIN=1`: this lets the emailed sign-in through. The backend refuses it unless `SUPABASE_URL` is local.

   Leave `FUNDTRAIL_ALLOWED_ORIGINS` empty. With a local `SUPABASE_URL`, the backend accepts calls from http://localhost:3000 and http://127.0.0.1:3000.
3. **Fill in the frontend's settings.** Copy `frontend/.env.example` to `frontend/.env.local`. The frontend reads only that file, not the root `.env`. Then set:
   - `NEXT_PUBLIC_API_URL`: `http://127.0.0.1:8000`.
   - `NEXT_PUBLIC_SUPABASE_URL`: `http://127.0.0.1:54321`.
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`: the publishable key that `supabase start` printed.
   - `NEXT_PUBLIC_DEV_EMAIL_SIGNIN=1`: this adds "Email me a link" to the sign-in page. A production build ignores it.
4. **Start the backend.** From `backend/`, run `uv sync`, then `uv run --env-file ../.env fastapi dev` (port 8000). The backend reads its settings from the environment and doesn't load `.env` itself, so `--env-file` is how they reach it.
5. **Start the frontend.** From `frontend/`, run `pnpm install`, then `pnpm dev` (port 3000).
6. **Sign in.** Open http://127.0.0.1:3000, enter an email address and choose "Email me a link". The link arrives in the local mail viewer at http://127.0.0.1:54324. Your first sign-in creates your workspace.

The lint, type check and test commands are in [CLAUDE.md, "Running things"](CLAUDE.md#running-things).

To look at the screens with sample data and no backend, set `NEXT_PUBLIC_FAKE=1` in `frontend/.env.local` instead. That mode has no agent, no checks and no timeline.

## Architecture

- **Frontend:** Next.js 16 (`frontend/`).
- **API (application programming interface):** FastAPI (`backend/app/api/`).
- **Agent:** a LangGraph graph calling Claude as `claude-opus-5-5` (`backend/app/agent/`).
- **Quotes:** finds each cited passage in its file, using pypdfium2 for PDFs, and cuts the boxed areas of photos and scanned pages for the second look (`backend/app/quotes/`).
- **Checks:** a pure function that sorts each charge into one of the four buckets, rerun on every record change (`backend/app/checks/`).
- **Benefits:** each benefit charge is recalculated from the confirmed benefit rate and that month's salary on the grant (`backend/app/checks/benefits.py`).
- **Ingest:** the ledger file, Gmail, Google Drive and uploads (`backend/app/ingest/`).
- **Jobs:** Procrastinate on Postgres, one lock per grant (`backend/app/db/jobs.py`).
- **Clock:** one clock per grant, real time for a real grant and simulated time for a sample (`backend/app/db/clock.py`).
- **Supabase:** Postgres, sign-in, file storage, and realtime pings that refresh the screen (`supabase/`).
- **Evidence report:** a PDF built with ReportLab (`backend/app/packet/`).
- **Samples:** the timeline and its player (`backend/app/samples/`), with two sample grants in `data/samples/`.

## Not built yet

- **The prerun sample**, with the agent's work done ahead of time. It shows as unavailable.
- **Word (.docx) files** aren't read yet.
- **The eval** has five cases with answer keys in `eval/cases/` but no runner yet. It has never been run, so there's no accuracy figure.
- **Gmail and Google Drive checking.** The checker is built but has never run live. It needs a Google account file and a mailbox (`GOOGLE_TOKEN_FILE`, `FUNDTRAIL_MAILBOX`). On a sample grant, the timeline plays the mail and file arrivals instead.
- **Accepting a grant problem.** Spending over the award's limit shows as a problem on the grant, but no screen can accept it with a note yet (issue 301).
- **Hosting.** There's no deploy config in the repo, and nothing has been deployed. Run it locally.

## For contributors and agents

Start with [CLAUDE.md](CLAUDE.md), then [docs/](docs/): [product](docs/product.md), [architecture](docs/architecture.md), [contracts](docs/contracts.md), [domain](docs/domain.md), [eval](docs/eval.md), [plan](docs/plan.md) and [decisions](docs/decisions/).
