# Architecture essay

*Form question: What does your architecture look like, and why did you choose the tools, models, and approach you did? What tradeoffs did you make, and what would you change with more time? (200 to 300 words)*

---

FundTrail automates the old way grant accountants prove spending followed the rules: piecing together spreadsheets, email chains and receipts by hand at closeout.

The approach: the agent judges, code checks. An espresso machine can pass every date and amount check and still be unallowable, so code asks the agent whether it's allowable, and the agent answers with quoted evidence. Clear-cut rules, such as dates and amounts, stay in code, which reads them the same way every time. Every quote is checked against its file. A value nobody can confirm never lets a charge pass; it goes to a person, because a misread is usually a confident one.

Each arrival from the ledger, Gmail, Google Drive or uploads queues a job on Procrastinate, a Postgres job queue with one lock per grant, so two runs never collide. The agent is a LangGraph graph calling Claude Opus 5.5. A pure function reruns every check whenever a record changes: when the accountant confirms an extension found in Drive, every late charge is rechecked at once. Next.js and FastAPI run the app on Supabase, and ReportLab builds the evidence report as a PDF (Portable Document Format).

We chose Claude because it reads PDFs, email and photos directly, with no OCR (optical character recognition) step, and its citations return the exact passage for code to find in the file. LangGraph lets each step call Claude directly, which keeps those citations intact.

Tradeoffs: the agent works from saved facts, so they are only as good as the first read. A crashed run starts over. Values read from receipt photos aren't confirmed automatically yet, so they go to a person.

With more time: resumable runs, a scored blind test, scanned PDFs and Word files, and funders beyond the National Science Foundation (NSF).
