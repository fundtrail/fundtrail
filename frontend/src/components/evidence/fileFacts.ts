// The viewer's "In this file": every value read from this file, in the card's
// order and words, each with a link to its own spot.

import type { EvidenceCard, Id } from "@/lib/api";
import { recordKindLabel } from "@/lib/format";
import { routes } from "@/lib/routes";
import { pageCaption } from "@/components/viewer/placement";
import type { FileFact, FileFactGroup } from "@/components/viewer/Viewer";
import { confirmationText, displayValue, isCited, valueAt, valueLabel } from "./values";

/** A fact's title as the card shows it: its kind, and its label when it has one. */
function factTitle(data: { kind: string; label?: unknown }): string {
  const kind = recordKindLabel(data.kind);
  return typeof data.label === "string" && data.label ? `${kind}: ${data.label}` : kind;
}

/**
 * The card's facts as the viewer lists them: only the values whose citation
 * is in this file. A record whose values cite two files is on both files'
 * cards, and a value from the other file has no spot here; a value with no
 * citation has no spot anywhere. `at` is the value the viewer is open at,
 * marked current. Confirmed values say nothing more; any other keeps the
 * card's words for its state. A fact with no value in this file isn't listed.
 */
export function fileFacts(grantId: Id, card: EvidenceCard, at: { recordId: Id | null; value: string | null }): FileFactGroup[] {
  const groups: FileFactGroup[] = [];
  for (const fact of card.facts ?? []) {
    const values: FileFact[] = [];
    for (const state of fact.values ?? []) {
      const cited = valueAt(fact.record.data, state.path);
      if (!isCited(cited) || !cited.citation || cited.citation.file_id !== card.file.id) continue;
      values.push({
        key: `${fact.record.id}:${state.path}`,
        label: valueLabel(state.path),
        value: displayValue(state.path, cited),
        location: pageCaption(cited.citation),
        note: state.confirmed ? null : confirmationText(state),
        href: routes.file(grantId, card.file.id, { recordId: fact.record.id, value: state.path }),
        current: at.recordId === fact.record.id && at.value === state.path,
      });
    }
    if (values.length > 0) {
      groups.push({ key: fact.record.id, title: factTitle(fact.record.data as { kind: string; label?: unknown }), values });
    }
  }
  return groups;
}
