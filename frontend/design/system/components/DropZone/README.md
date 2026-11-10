# DropZone

How files get into FundTrail when adding a grant: a drop zone, a row per file while the agent reads it, and what came out.

**Use it** for the award letter, the ledger file and evidence uploads.

- **Drop zone:** `button.ft-drop` with a bold instruction ("Drop the ledger file here") and one line on what it takes ("CSV or Excel, one file for this grant."). It is a button, so click and the keyboard open the file picker. While a file is dragged over it, add `is-over`: an `ink` dashed border and `paper-sunken`. `ft-drop--compact` is the smaller one for a second way in, such as evidence uploads next to the grant's email address.
- **File row:** `ft-file` with the name, a meta line (who uploaded it and when, or how many rows), and a state on the right. Reading shows the `ft-working-dot` and says what it's doing ("Reading 9 of 14"). Read shows a check.
- **Results:** `ul.ft-found` lists what the file produced ("38 charges added") with a check. Anything held back is `is-pending` with a dashed ring ("1 row skipped").
- **Skipped rows:** `ul.ft-errors`, one line per row: the row number in `ft-id`, then what's wrong in plain words. Under it, say how to fix it: "Fix the row and drop the file again. Lines already on file are skipped."
- **Copy field:** `ft-copy` holds an address in Geist Mono and a small Copy button, for the grant's own email address. Show the whole address; never cut it off.
- **Ways in:** `ft-ways` puts the evidence routes side by side (one column under 720px). Each `ft-way` has an `ft-heading`, one muted line, then its control: Forward email with the copy field, Upload with the compact drop zone.

Don't: show a progress percentage, color a skipped row red (it's not a conflict), or hide the file name once it's read.
