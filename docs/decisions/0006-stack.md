# 0006. Stack

**Date:** 2026-11-07 · **Status:** accepted

## Context

We chose each tool for fit, not for current familiarity, since the team can learn any stack. Citations need documents sent in the Anthropic API's own formats, including custom content documents. Pydantic AI can't send custom content documents. LangChain and LangGraph keep citations intact, and a LangGraph node is a plain function, so it can call the Anthropic SDK directly.

## Decision

| Part | Choice |
|---|---|
| Frontend | Next.js on Vercel |
| Document viewer | PDF.js (for example react-pdf) with a highlight layer |
| Backend | Python FastAPI on Railway, always on |
| Database, sign-in, file storage | Supabase (Postgres, Google sign-in, storage) |
| Model | Claude `claude-opus-5-5` |
| Agent | LangGraph, with the read step calling Anthropic's SDK directly |
| Records | Pydantic models |
| Connectors | Gmail API, Google Drive API |

## Consequences

- Railway keeps the backend running all the time, so long agent runs and connector checks aren't cut off by serverless time limits.
- Supabase covers the database, sign-in and file storage in one service.
- The frontend's API types are generated from FastAPI's OpenAPI schema (see [contracts.md](../contracts.md)).
