import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PdfPagesProps } from "./PdfPages";
import type { CitationLike } from "./placement";
import { fileKind, Viewer } from "./Viewer";

// PDF.js can't run in jsdom. The stand-in draws two pages and whatever the
// viewer overlays on each, which is the part under test.
vi.mock("./PdfPages", () => ({
  default: ({ overlay, targetPage }: PdfPagesProps) => (
    <div data-testid="pdf">
      {[1, 2].map((n) => (
        <div key={n} data-testid={`pdf-page-${n}`} data-scroll-target={n === targetPage ? "true" : undefined}>
          {overlay(n)}
        </div>
      ))}
    </div>
  ),
}));

const textUrl = (text: string) => `data:text/plain;charset=utf-8,${encodeURIComponent(text)}`;

const INVOICE = [
  "Example Lab Supply Co.",
  "Invoice Number: INV-1001",
  "Sediment core liners, 50 count: $1,240.00",
  "Total Due: $1,240.00",
].join("\n");

function charCitation(passage: string, text: string, highlight: [number, number][] | null, match: CitationLike["match"] = "exact"): CitationLike {
  const start = text.indexOf(passage);
  return {
    file_id: "f",
    passage,
    location: { type: "char_location", start_char_index: start, end_char_index: start + passage.length },
    match,
    highlight: highlight?.map(([s, e]) => ({ start_char_index: start + s, end_char_index: start + e })) ?? null,
  };
}

describe("fileKind", () => {
  it("reads the media type, and a .docx by name too", () => {
    expect(fileKind("message/rfc822")).toBe("text");
    expect(fileKind("text/plain")).toBe("text");
    expect(fileKind("application/pdf")).toBe("pdf");
    expect(fileKind("image/jpeg")).toBe("image");
    expect(fileKind("application/vnd.openxmlformats-officedocument.wordprocessingml.document")).toBe("docx");
    expect(fileKind("application/octet-stream", "budget_justification.docx")).toBe("docx");
  });
});

describe("Viewer: text and email", () => {
  it("highlights exactly the stored ranges, several of them", async () => {
    const passage = "Sediment core liners, 50 count: $1,240.00\nTotal Due: $1,240.00";
    // Two ranges: the amount on each line.
    const c = charCitation(passage, INVOICE, [
      [32, 41],
      [53, 62],
    ]);
    render(<Viewer file={{ name: "invoice.txt", media_type: "text/plain" }} url={textUrl(INVOICE)} citation={c} valueText="$1,240.00" />);
    const text = await screen.findByTestId("viewer-text");
    const marks = text.querySelectorAll("mark");
    expect([...marks].map((m) => m.textContent)).toEqual(["$1,240.00", "$1,240.00"]);
    expect(marks[0]).toHaveAttribute("data-scroll-target", "true");
    expect(marks[1]).not.toHaveAttribute("data-scroll-target");
    expect(text.textContent).toBe(INVOICE);
    expect(screen.queryByRole("note")).not.toBeInTheDocument();
  });

  it("highlights the cited characters when no finer ranges were stored", async () => {
    const email = "From: core@sequencing.example\r\nSubject: Statement\r\n\r\nTotal: $2,180.00\r\n";
    const c = charCitation("Total: $2,180.00", email, null);
    render(<Viewer file={{ name: "statement.eml", media_type: "message/rfc822" }} url={textUrl(email)} citation={c} />);
    const text = await screen.findByTestId("viewer-text");
    expect([...text.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["Total: $2,180.00"]);
  });

  it("counts characters as the server does, so text after an emoji still lines up", async () => {
    const body = "Thanks 👍 approved: $300.00";
    // The server's index counts the emoji as one character, JavaScript as two.
    const cpStart = [...body.slice(0, body.indexOf("$"))].length;
    expect(cpStart).toBe(body.indexOf("$") - 1);
    const c: CitationLike = {
      file_id: "f",
      passage: "$300.00",
      location: { type: "char_location", start_char_index: cpStart, end_char_index: cpStart + 7 },
      match: "exact",
      highlight: null,
    };
    render(<Viewer file={{ name: "approval.eml", media_type: "message/rfc822" }} url={textUrl(body)} citation={c} />);
    const text = await screen.findByTestId("viewer-text");
    expect(text.querySelector("mark")?.textContent).toBe("$300.00");
  });

  it("keeps a leading byte order mark, as the server's character indexes count it", async () => {
    const text = "﻿Total Due: $1,240.00";
    // Index 0 is the mark, so the passage starts at 1.
    const c = charCitation("Total Due: $1,240.00", text, [[11, 20]]);
    expect(c.location).toMatchObject({ start_char_index: 1 });
    render(<Viewer file={{ name: "invoice.txt", media_type: "text/plain" }} url={textUrl(text)} citation={c} />);
    const shown = await screen.findByTestId("viewer-text");
    expect(shown.querySelector("mark")?.textContent).toBe("$1,240.00");
  });

  it("words an unplaced value from its card's state, not from the citation", async () => {
    const c = charCitation("Total Due: $1,240.00", INVOICE, null, "not_found");
    render(
      <Viewer
        file={{ name: "invoice.txt", media_type: "text/plain" }}
        url={textUrl(INVOICE)}
        citation={c}
        confirmation={{ confirmed: true, text: "Confirmed by the accountant, Mar 20, 2026" }}
      />,
    );
    await screen.findByTestId("viewer-text");
    expect(screen.getByTestId("value-state")).toHaveTextContent("Confirmed by the accountant, Mar 20, 2026");
    expect(screen.getByRole("note")).toHaveTextContent("couldn't be placed in the file.");
    expect(screen.getByRole("note")).not.toHaveTextContent("unconfirmed");
  });

  it("shows a .docx's passage with the exact ranges highlighted and a link to the original", () => {
    const stored = "Budget justification\nTravel: two trips to the field site, $3,400 in all.";
    const passage = "Travel: two trips to the field site, $3,400 in all.";
    const c = charCitation(passage, stored, [[37, 43]]);
    render(
      <Viewer
        file={{ name: "budget_justification.docx", media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" }}
        url="https://storage.example/signed/budget_justification.docx"
        citation={c}
      />,
    );
    const text = screen.getByTestId("viewer-text");
    expect(text.textContent).toBe(passage);
    expect([...text.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["$3,400"]);
    expect(screen.getByRole("link", { name: "Download the original" })).toHaveAttribute(
      "href",
      "https://storage.example/signed/budget_justification.docx",
    );
  });

  it("opens a text fact that couldn't be placed with no highlight and the quote beside it", async () => {
    const c = charCitation("Total Due: $1,240.00", INVOICE, null, "not_found");
    render(<Viewer file={{ name: "invoice.txt", media_type: "text/plain" }} url={textUrl(INVOICE)} citation={c} />);
    const text = await screen.findByTestId("viewer-text");
    expect(text.querySelectorAll("mark")).toHaveLength(0);
    expect(screen.getByRole("note")).toHaveTextContent("Nothing is highlighted");
    expect(screen.getByTestId("side-quote")).toHaveTextContent("Total Due: $1,240.00");
    expect(screen.getByTestId("side-quote").querySelectorAll("mark")).toHaveLength(0);
  });

  it("marks only the value's own characters in the side quote", async () => {
    const passage = "Sediment core liners, 50 count: $1,240.00";
    const c = charCitation(passage, INVOICE, [[32, 41]]);
    render(<Viewer file={{ name: "invoice.txt", media_type: "text/plain" }} url={textUrl(INVOICE)} citation={c} />);
    await screen.findByTestId("viewer-text");
    const side = screen.getByTestId("side-quote");
    expect(side.textContent).toBe(passage);
    expect([...side.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["$1,240.00"]);
  });
});

describe("Viewer: PDF with real text", () => {
  const pdf = { name: "award_letter.pdf", media_type: "application/pdf" };

  it("outlines the stored boxes on their pages", async () => {
    const c: CitationLike = {
      file_id: "f",
      passage: "Total Amount Obligated to Date: $450,000",
      location: { type: "page_location", start_page_number: 2, end_page_number: 3 },
      match: "close",
      highlight: [
        { page: 2, left: 0.1, top: 0.4, width: 0.5, height: 0.03 },
        { page: 2, left: 0.1, top: 0.43, width: 0.3, height: 0.03 },
      ],
    };
    render(<Viewer file={pdf} url="https://storage.example/a.pdf" citation={c} />);
    const page2 = await screen.findByTestId("pdf-page-2");
    const boxes = within(page2).getAllByTestId("highlight-box");
    expect(boxes).toHaveLength(2);
    expect(boxes[0]).toHaveStyle({ left: "10%", top: "40%", width: "50%" });
    expect(boxes[0]).toHaveAttribute("data-scroll-target", "true");
    // A passage with real text is a highlighter over the page, not an outlined box.
    expect(boxes[0].parentElement).toHaveAttribute("data-variant", "mark");
    expect(within(screen.getByTestId("pdf-page-1")).queryAllByTestId("highlight-box")).toHaveLength(0);
    expect(within(screen.getByTestId("viewer-bar")).getByText("Close match on the page")).toBeInTheDocument();
  });

  it("names the marked box for a screen reader, once per passage", async () => {
    const c: CitationLike = {
      file_id: "f",
      passage: "Total Amount Obligated to Date: $450,000",
      location: { type: "page_location", start_page_number: 2, end_page_number: 3 },
      match: "exact",
      highlight: [
        { page: 2, left: 0.1, top: 0.4, width: 0.5, height: 0.03 },
        { page: 2, left: 0.1, top: 0.43, width: 0.3, height: 0.03 },
      ],
    };
    render(<Viewer file={pdf} url="https://storage.example/a.pdf" citation={c} label="Obligated to date" />);
    const page2 = await screen.findByTestId("pdf-page-2");
    expect(within(page2).getByRole("img", { name: "Obligated to date, highlighted passage" })).toBeInTheDocument();
    expect(within(page2).getAllByRole("img")).toHaveLength(1);
  });

  it("puts an exact quote on the highlighter in the side panel", async () => {
    const c: CitationLike = {
      file_id: "f",
      passage: "Total Due: $3,400.00",
      location: { type: "page_location", start_page_number: 2, end_page_number: 3 },
      match: "exact",
      highlight: [{ page: 2, left: 0.5, top: 0.4, width: 0.2, height: 0.03 }],
    };
    render(<Viewer file={pdf} url="https://storage.example/a.pdf" citation={c} valueText="$3,400.00" />);
    await screen.findByTestId("pdf-page-2");
    expect(screen.getByTestId("side-quote").querySelector("mark")).toHaveTextContent("Total Due: $3,400.00");
    expect(within(screen.getByRole("complementary", { name: "The quote" })).queryByText("Close match on the page")).toBeNull();
  });

  it("shows a close match's quote plain, with the bar's words for it, and keeps the mark on the page", async () => {
    const c: CitationLike = {
      file_id: "f",
      passage: "Boat and dock use for sediment coring,\ntwo days, March 2 to March 3, 2026",
      location: { type: "page_location", start_page_number: 1, end_page_number: 2 },
      match: "close",
      highlight: [{ page: 1, left: 0.1, top: 0.5, width: 0.4, height: 0.03 }],
    };
    render(<Viewer file={pdf} url="https://storage.example/a.pdf" citation={c} valueText="Boat and dock use" />);
    const page1 = await screen.findByTestId("pdf-page-1");
    expect(within(page1).getAllByTestId("highlight-box")).toHaveLength(1);
    const side = screen.getByRole("complementary", { name: "The quote" });
    expect(screen.getByTestId("side-quote").querySelector("mark")).toBeNull();
    expect(within(side).getByText("Close match on the page")).toBeInTheDocument();
  });

  it("opens an unplaced PDF fact at its page, with the quote beside it and no box", async () => {
    const c: CitationLike = {
      file_id: "f",
      passage: "The period of performance ends January 31, 2027.",
      location: { type: "page_location", start_page_number: 2, end_page_number: 3 },
      match: "not_found",
      highlight: null,
    };
    render(<Viewer file={pdf} url="https://storage.example/a.pdf" citation={c} valueText="January 31, 2027" />);
    const page2 = await screen.findByTestId("pdf-page-2");
    expect(page2).toHaveAttribute("data-scroll-target", "true");
    expect(screen.queryAllByTestId("highlight-box")).toHaveLength(0);
    expect(screen.getByRole("note")).toHaveTextContent("open at page 2");
    expect(screen.getByTestId("side-quote")).toHaveTextContent("The period of performance ends January 31, 2027.");
  });

  it("guesses nothing for a PDF match with no stored boxes", async () => {
    const c: CitationLike = {
      file_id: "f",
      passage: "Award Number: SYN-2300117",
      location: { type: "page_location", start_page_number: 1, end_page_number: 2 },
      match: "exact",
      highlight: null,
    };
    render(<Viewer file={pdf} url="https://storage.example/a.pdf" citation={c} />);
    await screen.findByTestId("pdf-page-1");
    expect(screen.queryAllByTestId("highlight-box")).toHaveLength(0);
    expect(screen.getByTestId("pdf-page-1")).toHaveAttribute("data-scroll-target", "true");
  });
});

describe("Viewer: photos and scans", () => {
  const box = (match: CitationLike["match"], page = 1): CitationLike => ({
    file_id: "f",
    passage: null,
    location: { type: "image_box", page, left: 0.6, top: 0.7, width: 0.25, height: 0.05 },
    match,
    highlight: null,
  });

  it("outlines a box on a photo, zoomed in, with the value beside it", () => {
    render(<Viewer file={{ name: "receipt.jpg", media_type: "image/jpeg" }} url="data:image/png;base64,iVBORw0KGgo=" citation={box("exact")} valueText="$86.40" />);
    const b = screen.getByTestId("highlight-box");
    expect(b).toHaveStyle({ left: "60%", top: "70%", width: "25%", height: "5%" });
    expect(screen.getByText("200%")).toBeInTheDocument();
    expect(screen.getByText("Box checked by a second look")).toBeInTheDocument();
    expect(screen.getByTestId("side-quote")).toHaveTextContent("$86.40");
    // A photo has no passage: its value shows once, as the value, never as a quote.
    expect(screen.getAllByText("$86.40")).toHaveLength(1);
    expect(screen.queryByRole("blockquote")).toBeNull();
    expect(screen.getByRole("img", { name: "Value, box checked by a second look" })).toBeInTheDocument();
  });

  it("outlines a box on a scanned PDF page", async () => {
    render(<Viewer file={{ name: "scan.pdf", media_type: "application/pdf" }} url="https://storage.example/scan.pdf" citation={box("exact", 2)} />);
    const page2 = await screen.findByTestId("pdf-page-2");
    expect(within(page2).getAllByTestId("highlight-box")).toHaveLength(1);
    expect(within(page2).getByTestId("highlight-box").parentElement).toHaveAttribute("data-variant", "box");
  });

  it("draws no box when the second look didn't see the same value", () => {
    render(<Viewer file={{ name: "receipt.jpg", media_type: "image/jpeg" }} url="data:image/png;base64,iVBORw0KGgo=" citation={box("not_found")} valueText="$86.40" />);
    expect(screen.queryAllByTestId("highlight-box")).toHaveLength(0);
    expect(screen.getByRole("note")).toHaveTextContent("Nothing is highlighted");
    expect(screen.getByTestId("side-quote")).toHaveTextContent("$86.40");
  });
});


describe("Viewer: an email as the agent reads it (ruling 45)", () => {
  const STORED = "From: core@sequencing.example\nDate: Sat, 21 Feb 2026 09:12:00 -0800\nSubject: Statement\n\nTotal: $2,180.00\n";
  const READING = "From: core@sequencing.example\nDate: Tuesday, February 24, 2026\nSubject: Statement\n\nTotal: $2,180.00\n";
  const keptFrom = "From: core@sequencing.example\n".length;
  const reading = {
    text: READING,
    segments: [
      { stored_start: 0, reading_start: 0, length: keptFrom },
      {
        stored_start: STORED.indexOf("Subject:"),
        reading_start: READING.indexOf("Subject:"),
        length: STORED.length - STORED.indexOf("Subject:"),
      },
    ],
  };
  const file = { name: "statement.eml", media_type: "message/rfc822" };

  it("shows the reading text with the highlight carried over, and links the original", async () => {
    const c = charCitation("Total: $2,180.00", STORED, [[7, 16]]);
    render(<Viewer file={file} url={textUrl(STORED)} citation={c} valueText="$2,180.00" reading={reading} />);
    const text = await screen.findByTestId("viewer-text");
    expect(text.textContent).toBe(READING);
    expect([...text.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["$2,180.00"]);
    expect(within(screen.getByTestId("reading-note")).getByRole("link", { name: "Download the original" })).toHaveAttribute(
      "href",
      textUrl(STORED),
    );
  });

  it("highlights the replaced Date line for a value cited from the stored header", async () => {
    const c = charCitation("Sat, 21 Feb 2026", STORED, null);
    render(<Viewer file={file} url={textUrl(STORED)} citation={c} reading={reading} />);
    const text = await screen.findByTestId("viewer-text");
    expect([...text.querySelectorAll("mark")].map((m) => m.textContent)).toEqual(["Date: Tuesday, February 24, 2026"]);
  });

  it("shows the stored email as before when there's no reading text", async () => {
    const c = charCitation("Total: $2,180.00", STORED, [[7, 16]]);
    render(<Viewer file={file} url={textUrl(STORED)} citation={c} />);
    const text = await screen.findByTestId("viewer-text");
    expect(text.textContent).toBe(STORED);
    expect(screen.queryByTestId("reading-note")).not.toBeInTheDocument();
  });
});
