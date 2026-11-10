# 0012. Quotes are checked against the file, and highlights copy known patterns

**Date:** 2026-11-09 · **Status:** accepted. Amends [0004](0004-files-to-claude-as-is.md) and rule 2 of [0005](0005-four-trust-rules.md).

## Context

The accountant needs one thing from quoting: click a fact and see the right line highlighted, or the right part of a photo. The earlier design had gaps:

- Code checked that a value appeared in its quoted passage, but never that the passage was really in the file.
- On photos and scans, the box was the agent's estimate on an image the API may have resized, and nothing checked it.
- Rule 2 of [0005](0005-four-trust-rules.md) had photo values match their ledger line instead. That stopped working once one bill could pay part of a charge, or several charges.

We looked at how production systems do this instead of inventing our own. Anthropic's Citations API returns the quoted passage itself, with exact characters for plain text and page numbers for PDFs. It can't cite images or scanned PDFs. Anthropic's cookbook highlights a PDF citation by searching the page for the quoted passage. Google's LangExtract tries an exact match and then a close one, and records which worked. Anthropic's coordinates guide describes how to get reliable boxes on images: ask for pixel coordinates on an image you resized yourself. Systems that can't place a highlight return none and send the value to review.

## Decision

- **Text, email and .docx:** the API's citation gives the exact characters. Code checks that the text at those characters is the quoted passage and that the value is inside it.
- **PDFs with real text:** the API's citation gives the page and the passage. Code finds the passage in that page's text, by exact match first and then a close match, and records which.
- **Photos and scanned pages:** we turn each page into an image at a size we control and send that. The agent returns a pixel box around the value, and code scales it back to the original. A second look reads only the boxed area and has to see the same value.
- **Nothing is guessed.** A fact that can't be placed opens to its page with the quote shown beside it, and the fact is unconfirmed.
- **An unconfirmed fact can't make anything pass, and it isn't ignored.** Whatever rests on it goes to Needs a human until the accountant confirms the value or types the right one.
- **The match runs once, on the server,** when the record is saved. Where the highlight goes is stored, and the viewer only draws it.
- **Still no OCR** (optical character recognition). It's the fallback if the eval shows boxes on photos aren't reliable enough.

## Considered and set aside

- **Relying on the agent's confidence alone.** A misread is usually a confident one.
- **OCR first for photos and scans,** as document services such as AWS Textract and Reducto do. It gives exact boxes with a confidence score, but adds a service, and Anthropic documents a way to get boxes from the model directly. It stays the fallback.
- **Sending our own extracted lines to the model so a citation points at a known position.** The API allows it, but we found no documented use of it this way, and the model would lose the page images that tables and layout depend on.
- **A parsing service that returns boxes,** such as LlamaExtract or Reducto. It would replace Claude's own citations with a paid dependency.

## Consequences

- Trust rule 2 becomes "every quote is checked against its file." The ledger-line match for photo values is gone.
- [0004](0004-files-to-claude-as-is.md) changes for photos and scanned pages only: they're sent as images at a size we control. Other files still go as they are.
- The contracts change: a citation stores where its highlight goes and how it matched, a cited value is confirmed or unconfirmed, and the write check reads the file (see [contracts.md](../contracts.md#13-agreed-changes-not-yet-in-the-code)).
- Open details, discussed with Alex before that part is built: how loose the PDF match can be, quotes that cross a page break, the cost of the second look, and the fact that citations can't be combined with structured outputs. They're listed in [architecture.md](../architecture.md#not-decided-yet).

## Sources

- [Anthropic: Citations](https://platform.claude.com/docs/en/build-with-claude/citations)
- [Anthropic: PDF support](https://platform.claude.com/docs/en/build-with-claude/pdf-support)
- [Anthropic: Coordinates and bounding boxes](https://platform.claude.com/docs/en/build-with-claude/vision-coordinates)
- [Anthropic cookbook: Using citations](https://platform.claude.com/cookbook/misc-using-citations)
- [Google LangExtract](https://github.com/google/langextract)
