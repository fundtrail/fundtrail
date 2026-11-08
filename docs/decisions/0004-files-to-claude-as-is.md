# 0004. Files go to Claude as they are, with no OCR

**Date:** 2026-11-07 · **Status:** accepted

## Context

Claude reads PDFs, scanned PDFs and images directly. Its citations only work on text: PDFs with a text layer, plain text and custom content documents. Images and scanned PDFs can't be cited. Adding OCR (optical character recognition) first would mean extra machinery and a new source of errors.

## Decision

- Files are sent to Claude unchanged. The only exception is .docx, which Claude doesn't accept, so its text is extracted first.
- There's no OCR.
- For photos and scans, Claude estimates a box around each quote.

## Consequences

- Text gets an exact highlight in the viewer. Images get an approximate box.
- Values read from photos and scans have no passage to check against, so they must match their ledger line instead: the amount, the date or the vendor (trust rule 2).
- OCR stays a later addition, only if it's ever needed.
