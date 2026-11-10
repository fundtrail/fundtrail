# 0013. Stack additions and the structure of the repo

**Date:** 2026-11-10 · **Status:** accepted. Amends [0006](0006-stack.md).

## Context

[0006](0006-stack.md) picked the stack when the agent was one fixed read step. Decisions [0009](0009-agent-judges-code-checks.md) to [0012](0012-checked-quotes-and-highlights.md) changed what the stack has to do:

- The agent is a loop of actions now, so the choice of LangGraph needed a second look.
- Agent runs go one at a time per grant, and a question in a thread goes ahead of the queue. Nothing was chosen to run them.
- The accountant asks the agent something and waits for a reply. Nothing said how the reply reaches the screen.
- The server finds each quote in a PDF and turns scanned pages into images. The stack listed no library for that.
- How Gmail and Drive are checked was never decided.

Alex's bar for each tool: free or very cheap, production-ready over hand-rolled, and a setup that isn't heavy. Each choice below was checked against the tool's own docs and pricing on November 10, 2026.

## Decision

| Part | Choice |
|---|---|
| Agent loop | Keep LangGraph, with a step that calls Anthropic's SDK directly. Its saving of a run partway through is off for now. |
| Background jobs | Procrastinate, a Python job queue on the Postgres database we already have |
| Telling the screen something changed | A ping through Supabase Realtime. The screen then refetches from our API. |
| PDF and image work on the server | pypdfium2 for PDFs and Pillow for images |
| Checking Gmail and Drive | On a timer, every one to two minutes |
| Repo | One repo. The backend and the frontend each carry their own setup files. No monorepo tool. |

- **LangGraph stays.** It doesn't restrict the product, and it can earn its place later in complex agent workflows: resuming long closeout runs, parallel work, live progress, and quick questions in the middle of a run. With its mid-run saving off, a crashed run starts over. That's a setting, to turn on when runs get long.
- **Procrastinate** has what the design asks for built in. Jobs that share a lock run one at a time, which gives one run per grant. Each job has a priority, which puts a thread question first. It can't interrupt a job that's already running. Retries and scheduled jobs are built in, and its worker can run inside the backend. A job cut off by a restart is detected, and retrying it takes a small scheduled task from its docs.
- **The ping** is a small "something changed" message on a private channel. Supabase doesn't promise delivery, so the screen also refetches when it connects or reconnects. The free plan covers 200 connections at once and 2 million messages a month.
- **pypdfium2** reads a page's text, finds a passage with its position, and renders a page to an image. Its license puts no conditions on a closed-source product.
- **A timer** needs no extra Google setup and stays far inside the free limits, because the app owns one account. Push only says "something changed", so it can be added later on top of the same code. Google itself says to keep a timer as the fallback.
- **The repo** gets one new folder, `backend/app/quotes/`, for finding quotes in files, highlight positions, page images for scans, and the second look on photos. The Python setup moves into `backend/`. The frontend may use a `src/` folder.

## Considered and set aside

- **A plain loop on Anthropic's SDK in place of LangGraph.** It's less to set up. Alex chose to keep LangGraph for the workflows it could support later. The switch is cheap either way, since the actions and the checks are the same code.
- **Other job systems.** A hand-written worker over our own table is free but hand-rolled. DBOS is close, but it's a whole workflow framework that overlaps with LangGraph. Hatchet and Inngest are outside services. Supabase's queues have no priority. Celery needs Redis and still has no built-in "one at a time per key". Temporal is far more than runs of seconds to minutes need.
- **Other ways to update the screen.** Asking again every few seconds is simple but wasteful as users grow. Having the browser listen to database changes would mean letting it read the tables. A live connection to our own backend is ours to build and scale. Cloudflare Durable Objects is a building block on a second platform, worth another look if several accountants ever work on one grant at once.
- **PyMuPDF.** Its search handles words split across lines, and Anthropic's citations example uses it. But its maker says a hosted app with closed source has to open its source or buy a license.
- **Push notifications from Gmail and Drive.** More setup, a subscription to renew every week, and the same calls afterward.
- **A monorepo tool such as Turborepo or Nx.** They coordinate many JavaScript packages. This repo has one, next to a Python backend.

## Consequences

- [architecture.md](../architecture.md#stack) lists the full stack. The repo map in [CLAUDE.md](../../CLAUDE.md#repo-map) shows the structure.
- **pypdfium2 has to be tested early.** Alex's condition is that it does reasonably what PyMuPDF would. The known gap is a quote whose words are split across lines, which our own clean-up step has to handle. If it doesn't match quotes reliably on real PDFs, the choice comes back to Alex.
- Procrastinate adds its own tables to the database. How its jobs relate to the `agent_runs` table is a contract question, listed in [contracts.md](../contracts.md#not-decided-yet).
- Details that only change how a part is built are under "Not decided yet" in [architecture.md](../architecture.md#not-decided-yet). They're discussed with Alex before that part is built.

## Sources

- [LangGraph docs](https://docs.langchain.com/oss/python/langgraph/overview)
- [Procrastinate docs](https://procrastinate.readthedocs.io/en/stable/)
- [Supabase Realtime](https://supabase.com/docs/guides/realtime) and [pricing](https://supabase.com/pricing)
- [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) and [Artifex licensing for PyMuPDF](https://artifex.com/licensing)
- [Gmail push notifications](https://developers.google.com/workspace/gmail/api/guides/push) and [Drive push notifications](https://developers.google.com/workspace/drive/api/guides/push)
