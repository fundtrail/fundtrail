import type { Citation, EvidenceCard, FtRecord, Id } from "@/lib/api";
import { citationAt, isCited, valueAt, valueLabel } from "./values";

export interface Spot {
  citation: Citation;
  /** The value as the document writes it, when the path names a cited value. */
  valueText: string | null;
  label: string;
}

/**
 * The citation the viewer opens at: a value of a fact on the cards, or a link's
 * part (its path is "part"). Null when the cards don't hold it.
 */
export function findCitation(cards: readonly EvidenceCard[], recordId: Id, path: string): Spot | null {
  let record: FtRecord | undefined;
  for (const card of cards) {
    for (const fact of card.facts ?? []) {
      if (fact.record.id === recordId) record = fact.record;
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
  };
}
