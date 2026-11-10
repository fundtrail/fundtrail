// Evidence cards and the viewer's originals for the sample grant. Owned by the
// evidence screen's builder.
//
// One card per file that had arrived by FAKE_NOW, newest first: the extension
// notice with its waiting term, the usage statement and the invoice each with
// their bill and its link, and the award letter with its ten confirmed terms.
// The viewer's "original" is the document's text as a data: URL.
//
// Beside the sample grant's four text files, three synthetic files cover the
// viewer's other cases (product.md, Viewer): a PDF with real text (boxes on its
// pages, and a value that couldn't be placed), a photo of a receipt (a box,
// and a box the second look didn't confirm), and a .docx (several highlighted
// ranges, confirmed by the accountant). They hold no links, so no other screen
// has to agree with them.

import type { ApiClient } from "../client";
import type { Bill, Citation, EvidenceCard, EvidenceFile, FactView, FileLink, FtRecord, Id, Link, Note, PageBox, RecordState } from "../types";
import { SAMPLE_DOCUMENTS } from "./documents";
import { atNow, FAKE_NOW, fakeId, foundValues, sampleCharge, served, SAMPLE_GRANT_ID, WORKSPACE_ID } from "./sample";

/** The records read from a file: every record with a citation into it that isn't a link, judgment or confirmation. */
function readFrom(fileId: Id): FtRecord[] {
  const factKinds = new Set(["period_of_performance", "budget_line", "person", "approval_rule", "rate", "notice", "other_term", "bill", "approval", "note"]);
  return atNow.records.filter((r) => factKinds.has(r.data.kind) && JSON.stringify(r.data).includes(`"file_id":"${fileId}"`));
}

function stateOf(record: FtRecord): RecordState {
  return record.id === "rec-period-extension" ? "waiting" : "counts";
}

function fact(record: FtRecord): FactView {
  const links = atNow.records
    .filter((r): r is FtRecord<Link> => r.data.kind === "link" && r.data.record_id === record.id)
    .map((link) => ({ link, charge: sampleCharge(link.data.charge_id) }));
  return { record, state: stateOf(record), values: foundValues(record), links, status: null };
}

export function sampleEvidence(): EvidenceCard[] {
  return [...atNow.files]
    .sort((a, b) => b.arrived_at.localeCompare(a.arrived_at))
    .map((file): EvidenceCard => ({ file, facts: readFrom(file.id).map(fact), status: null, duplicate: null, files: {} }))
    .concat(EXTRA_CARDS)
    .sort((a, b) => b.file.arrived_at.localeCompare(a.file.arrived_at));
}

function dataUrl(text: string, mediaType: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return `data:${mediaType};charset=utf-8;base64,${btoa(binary)}`;
}

export function evidenceFake(): Pick<ApiClient, "listEvidence" | "uploadEvidence" | "getFileLink"> {
  const cards = sampleEvidence();
  return {
    listEvidence: (grantId) => served(grantId === SAMPLE_GRANT_ID ? cards : []),
    uploadEvidence: (grantId, _file, fileName) => {
      const id = fakeId("file");
      const file: EvidenceFile = {
        id,
        workspace_id: WORKSPACE_ID,
        grant_id: grantId,
        source: "upload",
        name: fileName,
        media_type: _file.type || "application/octet-stream",
        storage_path: `${WORKSPACE_ID}/${grantId}/${id}/${fileName}`,
        sha256: `fake-${id}`,
        arrived_at: FAKE_NOW,
      };
      if (grantId === SAMPLE_GRANT_ID) cards.unshift({ file, facts: [], status: null, duplicate: null, files: {} });
      return served(file);
    },
    getFileLink: (fileId) => {
      const file = cards.find((c) => c.file.id === fileId)?.file;
      const extra = EXTRA_ORIGINALS[fileId];
      if (file && extra) return served({ url: extra, media_type: file.media_type, expires_at: "2099-01-01T00:00:00Z" });
      const text = file ? SAMPLE_DOCUMENTS[file.name] : undefined;
      if (!file || text === undefined) return served<FileLink>(undefined);
      return served({ url: dataUrl(text, file.media_type), media_type: file.media_type, expires_at: "2099-01-01T00:00:00Z" });
    },
  };
}

// --- Synthetic files for the viewer's other cases ------------------------------

const PAGE_W = 612; // US Letter, in PDF points
const PAGE_H = 792;
const FONT = 11; // Courier: every character is 0.6em wide, so a box can be worked out exactly
const CHAR_W = FONT * 0.6;
const LINE_X = 72;
const FIRST_LINE_Y = 740;
const LINE_STEP = 16;

const PDF_PAGES: string[][] = [
  [
    "SYNTHETIC DEMO DOCUMENT. Not issued by any company.",
    "Created for the FundTrail sample grant.",
    "",
    "Example Field Station Services",
    "INVOICE",
    "Invoice Number: FS-2207",
    "Invoice Dt: 03/02/26",
    "Bill To: Dr. Robin Example, Example State University",
    "Award: SYN-2300117",
    "",
    "Description:",
    "Boat and dock use for sediment coring,",
    "two days, March 2 to March 3, 2026",
  ],
  [
    "Example Field Station Services, invoice FS-2207, page 2",
    "",
    "Boat and dock use, 2 days at $1,700.00:  $3,400.00",
    "",
    "Total Due: $3,400.00",
  ],
];

/** A small PDF with real text, built here so the fixture needs no binary file. */
export function syntheticPdf(pages: string[][]): string {
  const objects: string[] = [];
  const kids: number[] = [];
  objects[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  objects[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>";
  pages.forEach((lines, i) => {
    const pageObj = 4 + i * 2;
    const contentObj = pageObj + 1;
    kids.push(pageObj);
    const ops = lines
      .map((line, n) => (line ? `BT /F1 ${FONT} Tf ${LINE_X} ${FIRST_LINE_Y - n * LINE_STEP} Td (${line.replace(/[()\\]/g, "\\$&")}) Tj ET` : ""))
      .filter(Boolean)
      .join("\n");
    objects[pageObj] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${PAGE_W} ${PAGE_H}] /Resources << /Font << /F1 3 0 R >> >> /Contents ${contentObj} 0 R >>`;
    objects[contentObj] = `<< /Length ${ops.length} >>\nstream\n${ops}\nendstream`;
  });
  objects[2] = `<< /Type /Pages /Kids [${kids.map((k) => `${k} 0 R`).join(" ")}] /Count ${kids.length} >>`;

  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  for (let n = 1; n < objects.length; n++) {
    offsets[n] = pdf.length;
    pdf += `${n} 0 obj\n${objects[n]}\nendobj\n`;
  }
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length}\n0000000000 65535 f \n`;
  for (let n = 1; n < objects.length; n++) pdf += `${String(offsets[n]).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return pdf;
}

/** The box around `text` on a line of the synthetic PDF, as the server would store it. */
function pdfBox(page: number, line: number, text: string): PageBox {
  const col = PDF_PAGES[page - 1][line].indexOf(text);
  const baseline = FIRST_LINE_Y - line * LINE_STEP;
  return {
    page,
    left: (LINE_X + col * CHAR_W - 2) / PAGE_W,
    top: (PAGE_H - baseline - FONT) / PAGE_H,
    width: (text.length * CHAR_W + 4) / PAGE_W,
    height: (FONT + 5) / PAGE_H,
  };
}

/** A photo of a receipt, drawn as an image so the fixture needs no binary file. */
const RECEIPT_SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800" viewBox="0 0 600 800">
<rect width="600" height="800" fill="#f3efe6"/>
<g font-family="Courier New, monospace" fill="#222">
<text x="40" y="70" font-size="18">SYNTHETIC DEMO RECEIPT</text>
<text x="40" y="95" font-size="14">Not issued by any company.</text>
<text x="40" y="170" font-size="30">Example Bay Boat Rental</text>
<text x="40" y="215" font-size="20">03/05/2026  10:42</text>
<text x="40" y="320" font-size="22">Kayak, half day</text>
<text x="400" y="320" font-size="22">$62.00</text>
<text x="40" y="360" font-size="22">Life vest</text>
<text x="400" y="360" font-size="22">$24.40</text>
<text x="40" y="640" font-size="32">TOTAL</text>
<text x="300" y="640" font-size="32">$86.40</text>
</g>
</svg>`;

const DOCX_TEXT =
  "Budget Justification\nSYN-2300117, Sediment Microbiome Survey of Example Bay\n\n" +
  "G.6 Other: boat and dock use at the field station, two days per season, $1,700.00 a day.\n";

function charsCitation(fileId: Id, stored: string, passage: string, highlight: string[] = []): Citation {
  const start = stored.indexOf(passage);
  return {
    file_id: fileId,
    passage,
    location: { type: "char_location", start_char_index: start, end_char_index: start + passage.length },
    match: "exact",
    highlight: highlight.map((h) => {
      const at = stored.indexOf(h, start);
      return { start_char_index: at, end_char_index: at + h.length };
    }),
  };
}

function extraFile(id: Id, name: string, mediaType: string, arrivedAt: string, more: Partial<EvidenceFile> = {}): EvidenceFile {
  return {
    id,
    workspace_id: WORKSPACE_ID,
    grant_id: SAMPLE_GRANT_ID,
    source: "upload",
    name,
    media_type: mediaType,
    storage_path: `${WORKSPACE_ID}/${SAMPLE_GRANT_ID}/${id}/${name}`,
    sha256: `synthetic-${id}`,
    arrived_at: arrivedAt,
    ...more,
  };
}

function extraRecord<D extends Bill | Note>(id: Id, writtenAt: string, data: D): FtRecord<D> {
  return { id, workspace_id: WORKSPACE_ID, grant_id: SAMPLE_GRANT_ID, author: "agent", written_at: writtenAt, replaces_id: null, data };
}

const PDF_ID = "file-syn-field-station-invoice";
const PHOTO_ID = "file-syn-boat-receipt";
const DOCX_ID = "file-syn-budget-justification";

const pdfBill = extraRecord<Bill>("rec-syn-bill-fs-2207", "2026-03-04T16:00:00Z", {
  kind: "bill",
  total: {
    value: 340000,
    text: "$3,400.00",
    citation: {
      file_id: PDF_ID,
      passage: "Total Due: $3,400.00",
      location: { type: "page_location", start_page_number: 2, end_page_number: 3 },
      match: "exact",
      highlight: [pdfBox(2, 4, "$3,400.00")],
    },
  },
  vendor: {
    value: "Example Field Station Services",
    text: "Example Field Station Services",
    citation: {
      file_id: PDF_ID,
      passage: "Example Field Station Services",
      location: { type: "page_location", start_page_number: 1, end_page_number: 2 },
      match: "exact",
      highlight: [pdfBox(1, 3, "Example Field Station Services")],
    },
  },
  document_number: {
    value: "FS-2207",
    text: "FS-2207",
    citation: {
      file_id: PDF_ID,
      passage: "Invoice Number: FS-2207",
      location: { type: "page_location", start_page_number: 1, end_page_number: 2 },
      match: "exact",
      highlight: [pdfBox(1, 5, "FS-2207")],
    },
  },
  description: {
    value: "Boat and dock use for sediment coring, two days",
    text: "Boat and dock use for sediment coring,\ntwo days",
    citation: {
      file_id: PDF_ID,
      passage: "Boat and dock use for sediment coring,\ntwo days, March 2 to March 3, 2026",
      location: { type: "page_location", start_page_number: 1, end_page_number: 2 },
      match: "close",
      highlight: [pdfBox(1, 11, "Boat and dock use for sediment coring,"), pdfBox(1, 12, "two days, March 2 to March 3, 2026")],
    },
  },
  // The page writes "03/02/26"; the quote below isn't on it, so it couldn't be placed.
  dated: {
    value: "2026-03-02",
    text: "March 2, 2026",
    citation: {
      file_id: PDF_ID,
      passage: "Invoice Date: March 2, 2026",
      location: { type: "page_location", start_page_number: 1, end_page_number: 2 },
      match: "not_found",
      highlight: null,
    },
  },
});

const imageBox = (left: number, top: number, width: number, height: number, match: Citation["match"]): Citation => ({
  file_id: PHOTO_ID,
  passage: null,
  location: { type: "image_box", page: 1, left, top, width, height },
  match,
  highlight: null,
});

const photoBill = extraRecord<Bill>("rec-syn-bill-boat-receipt", "2026-03-05T19:00:00Z", {
  kind: "bill",
  total: { value: 8640, text: "$86.40", citation: imageBox(0.48, 0.75, 0.24, 0.065, "exact") },
  // The second look didn't see the same values in these boxes.
  vendor: { value: "Example Bay Boat Rentals", text: "Example Bay Boat Rentals", citation: imageBox(0.05, 0.17, 0.75, 0.06, "not_found") },
  dated: { value: "2026-03-06", text: "03/06/2026", citation: imageBox(0.05, 0.245, 0.33, 0.04, "not_found") },
});

const docxNote = extraRecord<Note>("rec-syn-note-budget-justification", "2026-03-01T18:00:00Z", {
  kind: "note",
  label: "Boat and dock use in the budget justification",
  statement: {
    value: "Boat and dock use at the field station, two days per season, $1,700.00 a day.",
    text: "boat and dock use at the field station, two days per season, $1,700.00 a day",
    citation: charsCitation(
      DOCX_ID,
      DOCX_TEXT,
      "G.6 Other: boat and dock use at the field station, two days per season, $1,700.00 a day.",
      ["boat and dock use at the field station", "$1,700.00 a day"],
    ),
  },
});

const found = (path: string, at: string) => ({ path, confirmed: true, how: "found" as const, confirmed_at: at });
const unconfirmed = (path: string) => ({ path, confirmed: false, how: null, confirmed_at: null });

const EXTRA_CARDS: EvidenceCard[] = [
  {
    file: extraFile(PDF_ID, "field_station_invoice_FS-2207.pdf", "application/pdf", "2026-03-04T15:30:00Z", { document_date: "2026-03-02" }),
    facts: [
      {
        record: pdfBill,
        state: "counts",
        values: [
          found("total", pdfBill.written_at),
          found("vendor", pdfBill.written_at),
          found("document_number", pdfBill.written_at),
          found("description", pdfBill.written_at),
          unconfirmed("dated"),
        ],
        links: [],
        status: null,
      },
    ],
    status: null,
    duplicate: null,
    files: {},
  },
  {
    file: extraFile(PHOTO_ID, "boat_rental_receipt.jpg", "image/svg+xml", "2026-03-05T18:20:00Z", {
      source: "gmail",
      sender: "robin.example@university.example",
    }),
    facts: [
      {
        record: photoBill,
        state: "counts",
        values: [found("total", photoBill.written_at), unconfirmed("vendor"), unconfirmed("dated")],
        links: [],
        status: null,
      },
    ],
    status: null,
    duplicate: null,
    files: {},
  },
  {
    file: extraFile(DOCX_ID, "budget_justification.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "2026-03-01T17:00:00Z", {
      source: "drive",
    }),
    facts: [
      {
        record: docxNote,
        state: "counts",
        values: [{ path: "statement", confirmed: true, how: "record_confirmed", confirmed_at: "2026-03-20T17:00:00Z" }],
        links: [],
        status: null,
      },
    ],
    status: null,
    duplicate: null,
    files: {},
  },
];

/** The originals of the synthetic files, as data: URLs. The .docx is served as its text. */
const EXTRA_ORIGINALS: Record<Id, string> = {
  [PDF_ID]: `data:application/pdf;base64,${btoa(syntheticPdf(PDF_PAGES))}`,
  [PHOTO_ID]: dataUrl(RECEIPT_SVG, "image/svg+xml"),
  [DOCX_ID]: dataUrl(DOCX_TEXT, "text/plain"),
};
