# Architecture essay

*Form question: What does your architecture look like, and why did you choose the tools, models, and approach you did? What tradeoffs did you make, and what would you change with more time? (200 to 300 words)*

---

FundTrail automates the old way grant accountants prove spending followed the rules: piecing together spreadsheets, email chains and receipts by hand at closeout.

**Architecture.** A Next.js frontend talks to a FastAPI backend. Supabase gives us Postgres, sign-in, file storage and live screen updates. Evidence arrives from the ledger file, Gmail, Google Drive and uploads, and each arrival queues a job on Procrastinate, which holds one lock per grant so two runs never collide. The agent is a LangGraph graph calling Claude Opus 5.5. It reads each file as is, with no OCR (optical character recognition), and writes records that cite exact passages. Code finds every quote in its file before trusting it. A pure function reruns every check whenever a record changes and sorts each charge into a bucket. ReportLab builds the evidence report as a PDF (Portable Document Format).

**Why.** The core split is that the agent judges and code checks. Clear-cut rules, such as dates and amounts, are code, because code doesn't misread. Judgment calls, such as whether a cost is reasonable, become specific questions the agent answers with citations. A value nobody can confirm against its source never passes; it goes to a person, because a misread is usually a confident one. We chose LangGraph because it keeps Anthropic's citations intact, and Procrastinate because per-grant locks and priorities come built in, with no extra queue server.

**Tradeoffs.** The agent works from saved facts, so they are only as good as the first read. A crashed run starts over instead of resuming. Receipt photos can't yet be confirmed automatically, so their amounts go to a person.

**With more time:** resumable runs, a scored blind test of the agent, scanned PDFs and Word files, and funders beyond the National Science Foundation (NSF).
