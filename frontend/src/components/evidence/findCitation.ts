import type { Citation, EvidenceCard, FtRecord, Id, ValueState } from "@/lib/api";
import { citationAt, confirmationText, isCited, valueAt, valueLabel } from "./values";

export interface Spot {
  citation: Citation;
  /** The value as the document writes it, when the path names a cited value. */
  valueText: string | null;
  label: string;
  /** The value's state as its card shows it; null for a link's part, which has none. */
  confirmation: { confirmed: boolean; text: string } | null;
}

/**
 * The citation the viewer opens at: a value of a fact on the cards, or a link's
 * part (its path is "part"). Null when the cards don't hold it.
 */
export function findCitation(cards: readonly EvidenceCard[], recordId: Id, path: string): Spot | null {
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
  if (!record) return null;
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
