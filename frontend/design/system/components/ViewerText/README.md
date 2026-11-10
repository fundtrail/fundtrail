# ViewerText

The viewer's body for a plain-text file: the whole file, every line with its number, scrolled to the active fact with its exact passage marked. The award letter and amendments are plain text in the demo.

**Use it** inside the viewer sheet (`ft-sheet__doc`) when a fact cites a `char_location` in a text file. The renderer is `FTViewer.text` in the viewer script built into this card and the Demo.

**The consumer provides** the file (`lines`, one string per line, blank lines kept) and its facts, each with `label`, `value`, `line` and `text` (the exact passage), plus which fact is active.

- The page is `paper-raised` with a thin `rule`, on the `paper-sunken` doc area. The text is the document serif; line numbers are Geist Mono in `ink-muted`, right-aligned in their own gutter. A long line wraps under its own number.
- Only the active fact's passage is marked: `mark.ft-mark-hl.is-active` around the exact text within its line. Its line number turns `ink` and bold. Other cited passages stay unmarked; they're reachable from "In this file" and the pager.
- The bar says what is open: the fact's label, "Exact passage", and its line.
- Opening centers the passage with no animation. Moving to another fact scrolls smoothly and the mark goes from `highlight` to `highlight-active` over 200ms; under reduced motion it jumps.
- The side list keeps the active fact in view.

Don't: crop the file to the passage, mark every cited passage at once, or drop the line numbers. The evidence report and the trail cite by line.

**Hash params, for screenshots:** `#fact=N` picks a fact by index, and `&t=dark` sets the dark theme.
