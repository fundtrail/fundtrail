# CitedPassage

The two ways a passage is marked in an original: the exact mark and the checked box. The full viewer around them (head, bar, pager, side list) is ViewerSheet, with ViewerText, ViewerEmail, ViewerPdf and ViewerPhoto for each kind of file.

- **Exact mark.** Text, email, PDFs with real text and .docx: `mark.ft-mark-hl.is-active` on the passage itself, `highlight-active` with `on-highlight` text. Only the active passage is marked.
- **Checked box.** Photos and scans: `ft-box`, a `highlight-wash` fill with an `ink` outline, around the value. The agent returns a pixel box and a second look reads only the boxed area and has to see the same value, so the caption is "Box checked by a second look". There is still no OCR (optical character recognition).
- **Unconfirmed.** A quote that couldn't be placed in its file gets no mark and no box: the viewer opens its page with the quote beside it, and the fact stays unconfirmed until the accountant confirms the value or types the right one (ViewerUnconfirmed).
- The original sits on `paper-raised` (`ft-page`) inside a `paper-sunken` frame.

Don't: crop the document to the passage. The user needs the surrounding text to judge it.
