// Evidence cards and the viewer's originals for the sample grant. Owned by the
// evidence screen's builder.
//
// One card per file that had arrived by FAKE_NOW, newest first: the extension
// notice with its waiting term, the usage statement and the invoice each with
// their bill and its link, and the award letter with its ten confirmed terms.
// The viewer's "original" is the document's text as a data: URL.

import type { ApiClient } from "../client";
import type { EvidenceCard, EvidenceFile, FactView, FileLink, FtRecord, Id, Link, RecordState } from "../types";
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
    .map((file) => ({ file, facts: readFrom(file.id).map(fact), status: null, duplicate: null, files: {} }));
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
      const text = file ? SAMPLE_DOCUMENTS[file.name] : undefined;
      if (!file || text === undefined) return served<FileLink>(undefined);
      return served({ url: dataUrl(text, file.media_type), media_type: file.media_type, expires_at: "2099-01-01T00:00:00Z" });
    },
  };
}
