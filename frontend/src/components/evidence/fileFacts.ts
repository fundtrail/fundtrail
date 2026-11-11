// The viewer's "In this file": every value of every fact on a file's card, in
// the card's order and words, each with a link to its own spot.

import type { EvidenceCard, Id } from "@/lib/api";
import { recordKindLabel } from "@/lib/format";
import { routes } from "@/lib/routes";
import { pageCaption } from "@/components/viewer/placement";
import type { FileFactGroup } from "@/components/viewer/Viewer";
import { confirmationText, displayValue, isCited, valueAt, valueLabel } from "./values";

/** A fact's title as the card shows it: its kind, and its label when it has one. */
function factTitle(data: { kind: string; label?: unknown }): string {
  const kind = recordKindLabel(data.kind);
  return typeof data.label === "string" && data.label ? `${kind}: ${data.label}` : kind;
}

/**
 * The card's facts as the viewer lists them. `at` is the value the viewer is
 * open at, marked current. A value with no citation has no spot to open, so
 * it has no link. Confirmed values say nothing more; any other keeps the
 * card's words for its state.
 */
export function fileFacts(grantId: Id, card: EvidenceCard, at: { recordId: Id | null; value: string | null }): FileFactGroup[] {
  return (card.facts ?? []).map((fact) => ({
    key: fact.record.id,
    title: factTitle(fact.record.data as { kind: string; label?: unknown }),
    values: (fact.values ?? []).map((state) => {
      const cited = valueAt(fact.record.data, state.path);
      const citation = isCited(cited) ? (cited.citation ?? null) : null;
      return {
        key: `${fact.record.id}:${state.path}`,
        label: valueLabel(state.path),
        value: isCited(cited) ? displayValue(state.path, cited) : null,
        location: citation ? pageCaption(citation) : null,
        note: state.confirmed ? null : confirmationText(state),
        href: citation ? routes.file(grantId, citation.file_id, { recordId: fact.record.id, value: state.path }) : null,
        current: at.recordId === fact.record.id && at.value === state.path,
      };
    }),
  }));
}
