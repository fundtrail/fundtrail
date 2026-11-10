# EvidenceReport

One PDF per grant that shows why each charge was allowed. The accountant attaches it to the university's closeout step (Berkeley's Award Closeout Certification), next to the university's ledger report, which shows only what was spent. The National Science Foundation (NSF) doesn't require it and never receives it. The name, the layout and the sign-off flow are proposals: docs/product.md lists them as not decided.

**Page plan** for SYN-2300117, 9 US Letter pages:

1. **Summary:** the award, its dates with the amendment note, the recipient, the PI, the amount awarded, the total of all charges (matches the ledger report), the number of charges and the count in each bucket, budget by line, what the report is for, and how to read it.
2. **All charges,** pages 2 and 3: one row per charge in date order, with the header repeated and a totals row at the end.
3. **Charge sections,** pages 4 to 6, two per page: the checks, the evidence quoted from its sources with locations, the answers labeled Agent or Accountant, and the status history.
4. **Open at sign-off and Sign-off,** page 7: the open charges with what would close each, Prepared by, and the Reviewed by block with blank signature and date lines.
5. **Sources,** pages 8 and 9: every file the report cites, where it came from, when it arrived and which charges cite it.

**How it's built.** Each part is an HTML fragment of `ft-rpage` sections in the design system's working folder (`components/_src/report-summary.html`, `report-table.html`, `report-sections.html`, `report-signoff.html`, `report-sources.html`, each with optional CSS). The tooling script `build_report.py` joins them in page order inside `main.ft-report` and writes this card's `preview.html`. Edit a fragment and rebuild; never edit `preview.html` by hand. The fragments' CSS is merged into `components/bundle.css` when the system is published. Every number comes from `report-data.json` (51 charges, $96,412.18).

**Classes:** `ft-report`, `ft-rpage` with `__head`, `__body` and `__foot`, `ft-rdraft`, `ft-rtable` (`num` cells, `tfoot` totals) and `ft-rkv`.

**Data it shows:** the grant and its confirmed terms, each charge's ledger line, date, description, amount and budget assignment, its current bucket and reasons, judgments (answer, reasoning, author, quotes), links with their citations (file, passage, location), the status history, the `sign_off` record (note, author, time), and each evidence file's name, source and `arrived_at`. The app gets it from `GET /grants/{grant_id}/report`.

**Hash params, for screenshots:** `#page=N` scrolls to page N. `#signed=1` shows the signed version (`html.is-signed`: Draft hides and the head reads "Signed off"). `#t=dark` sets the dark theme.

**Mock scope.** Charge sections are written for six charges: L-1002, L-0981, L-1010, L-1019, L-1015 and L-1001. The other 45 charges' sections are left out of this mock, and page 6 says they follow the same layout. A real report has one section per charge, so its page count grows with the grant.

Don't: type a number by hand, put a paraphrase in quote marks, let color alone mark an open charge, or write "Submitted", "Filed" or "Certified".

**Following PR 6 (not merged yet).** Each charge section's checks start with its evidence checklist ("A bill that adds up", plus items such as a required approval), and a Decisions block lists what the accountant decided on that charge (L-1002: amendment 01 confirmed). Quotes are described as checked against their file, with photos boxed and checked by a second look; nothing says "approximate". Conversations with the agent stay out of the report; only decisions go in.
