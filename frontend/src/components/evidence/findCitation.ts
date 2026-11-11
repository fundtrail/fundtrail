import type { Citation, EvidenceCard, FtRecord, Id, ValueState } from "@/lib/api";
import { citationAt, confirmationText, isCited, valueAt, valueLabel } from "./values";

export interface Spot {
  citation: Citation;
  /** The value as the document writes it, when the path names a cited value. */
  valueText: string | null;
  label: string;
  /** The value's state as its card shows it; null for a link's part or an answer's quote, which have none. */
  confirmation: { confirmed: boolean; text: string } | null;
}

/** "quotes[2]" -> 2, for an answer's quote; null for any other path. */
function quoteIndex(path: string): number | null {
  const m = /^quotes\[(\d+)\]$/.exec(path);
  return m ? Number(m[1]) : null;
}

/**
 * The citation the viewer opens at: a value of a fact on the cards, a link's
 * part (its path is "part"), or one of an answer's quotes (a judgment record,
 * path "quotes[i]"). Answers aren't on the evidence cards, so they're looked
 * up in `records` (GET /grants/{grant_id}/records, `useRecords` in lib/api)
 * when the caller passes them.
 * Null when none of them holds it.
 */
export function findCitation(
  cards: readonly EvidenceCard[],
  recordId: Id,
  path: string,
  records: readonly FtRecord[] = [],
): Spot | null {
  let record: FtRecord | undefined;
  let state: ValueState | undefined;
  for (const card of cards) {
    for (const fact of card.facts ?? []) {
      if (fact.record.id === recordId) {
        record = fact.record;
        state = fact.values?.find((v) => v.path === path);
      }
      const link = fact.links?.find((l) => l.link.id === recordId);
      if (link) record = link.link;
    }
  }
  if (!record) {
    // An answer's quote: only a judgment, and only by its quotes' index.
    const index = quoteIndex(path);
    const judgment = records.find((r) => r.id === recordId && r.data.kind === "judgment");
    if (index === null || !judgment) return null;
    const citation = citationAt(judgment.data, path);
    if (!citation) return null;
    return { citation, valueText: null, label: `Quote ${index + 1} in the answer`, confirmation: null };
  }
  const citation = citationAt(record.data, path);
  if (!citation) return null;
  const v = valueAt(record.data, path);
  return {
    citation,
    valueText: isCited(v) ? (v.text ?? null) : null,
    label: record.data.kind === "link" && path === "part" ? "The part for this charge" : valueLabel(path),
    confirmation: state ? { confirmed: state.confirmed, text: confirmationText(state) } : null,
  };
}
