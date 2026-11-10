# ViewerEmail

The viewer's body for an email (.eml): its headers, then the body, scrolled to the active fact with its exact passage marked. Approvals and forwarded invoices usually arrive this way.

**Use it** inside the viewer sheet (`ft-sheet__doc`) when a fact cites an email. The renderer is `FTViewer.email` in the viewer script built into this card and the Demo.

**The consumer provides** the raw lines of the .eml and its facts, each with `label`, `value`, `line` and `text`, like ViewerText.

- Headers come first as quiet key-value rows in the interface font: From, To, Subject (bold) and Date. Content-Type and other technical headers are hidden. A rule separates them from the body.
- The body is the document serif. A quoted reply line (">") shows as a quote: `ink-muted` with a `rule-strong` bar, without the ">".
- Line numbers stay, quieter than in a text file, because citations count the file's real lines, headers included. Hidden headers leave a gap in the numbers on purpose.
- A fact can sit in a header. The approver's address in From is marked like any passage, since code matches senders against the people in the award letter.
- The side list's "Linked to" names the charge and what the email is to it, for example "Approval".

Don't: render the email as one block of raw text, or hide who sent it. The sender is often the fact that decides the charge.

**Hash params, for screenshots:** `#fact=N` picks a fact by index, and `&t=dark` sets the dark theme.
