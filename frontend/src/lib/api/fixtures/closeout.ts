// Closeout for the sample grant: the evidence report. Owned by the closeout
// screen's builder. The sample's sign-off state is SAMPLE_SIGN_OFF in
// sample.ts, shared with the grant page.
//
// The report is a one-page placeholder PDF that says it's fake; the real one
// is W6's.

import type { ApiClient } from "../client";
import { served, SAMPLE_GRANT_ID } from "./sample";

/** A minimal valid PDF with one line of text. */
function placeholderPdf(line: string): Blob {
  const text = line.replace(/[()\\]/g, "");
  const stream = `BT /F1 14 Tf 72 720 Td (${text}) Tj ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
  ];
  let pdf = "%PDF-1.4\n";
  const offsets: number[] = [];
  objects.forEach((body, i) => {
    offsets.push(pdf.length);
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const o of offsets) pdf += `${String(o).padStart(10, "0")} 00000 n \n`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return new Blob([pdf], { type: "application/pdf" });
}

export function closeoutFake(): Pick<ApiClient, "getReport"> {
  return {
    getReport: (grantId) =>
      grantId === SAMPLE_GRANT_ID
        ? Promise.resolve(placeholderPdf("Fake mode: placeholder evidence report for SYN-2300117. Synthetic data."))
        : served<Blob>(undefined),
  };
}
