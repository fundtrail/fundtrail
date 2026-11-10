# The from-scratch seed pack

The files in `pack/` are what the user drops into the demo workspace to add a grant from scratch ([0024](../../docs/decisions/0024-the-seeded-demo-workspace.md)). Everything is synthetic.

**The grant:** SYN-2511958, "Low-Cost Nitrate Sensors for Example Valley Groundwater", from September 1, 2025 to August 31, 2028, with $40,000 for travel and supplies.

| File | What it is |
|---|---|
| `award_letter.pdf` | The award notice, laid out like a real National Science Foundation (NSF) notice |
| `ledger.csv` | Seven ledger lines in the format of contracts.md section 13 |
| `invoice_EES-5531.pdf`, `invoice_EES-6012.pdf`, `invoice_EES-7420.pdf` | Vendor invoices |
| `email_invoice_ESS-31877.eml`, `email_invoice_ESS-32410.eml` | Invoices the professor forwarded by email |
| `airfare_receipt_valley-wells-2026.eml`, `hotel_folio_valley-wells-2026.pdf`, `expense_report_valley-wells-2026.txt` | A field trip's receipts and expense report |
| `hardware_receipt.jpg` | A phone photo of a paper receipt from a hardware store |

**Later lines.** Two ledger lines post after the demo's opening date: L-1958-0006 on November 24, 2026 and L-1958-0007 on December 7, 2026. Their invoices are already in the pack, so they wait unlinked until the clock releases the lines.

**The key** (`answer_key.json`, `arrivals.json`) assumes this script on the opening date, November 16, 2026: the user uploads the award letter at 17:30 UTC (Coordinated Universal Time), confirms its terms, uploads the ledger at 17:45 and then the other files, one a minute. The five lines already past their posting date arrive with the ledger ([0023](../../docs/decisions/0023-the-clock.md)). `pack.json` holds the ledger's upload time. Every line is expected in Evidence complete once its evidence is on file.
