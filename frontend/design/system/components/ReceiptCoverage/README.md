# ReceiptCoverage

The bills, approvals and explaining emails that pay for or explain a charge, with how much of each bill this charge uses. A bill is any invoice, receipt or card slip.

**The consumer provides** the charge's links (`LinkView` in the API): each linked fact's file name, vendor or sender, the amount this charge uses and the bill's total, plus the charge amount for the total line.

- A bill that this charge uses only part of reads "$5,833.33 of $10,000.00", the part in `body-strong`, with a bar showing the used part in `ledger` on a `paper-sunken` track.
- A bill that covers the whole charge reads "$2,180.00, the full charge", with no bar.
- An approval or explaining email states what it gives ("56 of 96 samples") with a Source link, instead of a bar.
- Each name opens the viewer with the part for this charge highlighted.
- The total line compares what is covered with what was charged. When they differ, the charge's reasons say so; this component doesn't change color.

Don't: color the bar by bucket, or round amounts.

Inside a charge's details, the Trail shows each bill as a link; use this component where bills are listed on their own, such as the Evidence page and the evidence report.
