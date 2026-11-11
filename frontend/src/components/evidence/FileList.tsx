"use client";

import Link from "next/link";
import type { MouseEvent } from "react";
import type { EvidenceCard, Id, RecordKind } from "@/lib/api";
import { date, SOURCE_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import styles from "./FileList.module.css";

/**
 * Picks a file for the page to show beside the list. Returning false lets the
 * row's link open the file's own page instead (a screen too narrow for both).
 */
export type OnSelectFile = (fileId: Id) => boolean;

/** Which rows show: every file, or only the files linked to no charge. */
export type FileFilter = "all" | "not_linked";

/** The kinds of fact a link ties to a charge: a bill pays for it, an approval approves it, a note supports it. */
const LINKABLE: ReadonlySet<RecordKind> = new Set<RecordKind>(["bill", "approval", "note"]);

/**
 * A file linked to no charge: it holds a fact that a link could tie to a
 * charge (a bill, an approval or a note), and none of its facts has a link.
 * Read from the card's own facts and their links, the lists the card's
 * "Linked to" lines come from. A file of grant terms isn't linked to charges,
 * so it's never in this filter.
 */
export function isNotLinked(card: EvidenceCard): boolean {
  const facts = card.facts ?? [];
  const linkable = facts.some((f) => LINKABLE.has(f.record.data.kind));
  return linkable && facts.every((f) => (f.links ?? []).length === 0);
}

/** The rows a filter shows, in the server's order. A filter only hides rows. */
export function cardsInFilter(cards: readonly EvidenceCard[], filter: FileFilter): EvidenceCard[] {
  return filter === "not_linked" ? cards.filter(isNotLinked) : [...cards];
}

/** What the card already knows about a file, in the card's own words. */
export function fileTags(card: EvidenceCard): { text: string; tone: "waiting" | "quiet" }[] {
  const facts = card.facts ?? [];
  const tags: { text: string; tone: "waiting" | "quiet" }[] = [];
  if (facts.some((f) => f.state === "waiting")) tags.push({ text: "Waiting for the accountant", tone: "waiting" });
  if (facts.some((f) => (f.values ?? []).some((v) => !v.confirmed))) tags.push({ text: "Unconfirmed", tone: "quiet" });
  if (card.duplicate) {
    const originalId = (card.duplicate.mark.data as { original_file_id: Id }).original_file_id;
    tags.push({ text: `Copy of ${card.files?.[originalId]?.name ?? "another file"}`, tone: "quiet" });
  }
  return tags;
}

/** The filter as pills for the page's head, with the count of rows the server sent in each. */
export function FileFilters({ cards, value, onChange }: { cards: readonly EvidenceCard[]; value: FileFilter; onChange: (filter: FileFilter) => void }) {
  const notLinked = cards.filter(isNotLinked).length;
  // A filter that would show every row, or none, isn't worth a pill.
  if (notLinked === 0 || notLinked === cards.length) return null;
  return (
    <div className={styles.pills} role="group" aria-label="Show on the evidence list">
      <button type="button" className={styles.pill} aria-pressed={value === "all"} onClick={() => onChange("all")}>
        All <span className={styles.count}>{cards.length}</span>
      </button>
      <button type="button" className={styles.pill} aria-pressed={value === "not_linked"} onClick={() => onChange("not_linked")}>
        Not linked <span className={styles.count}>{notLinked}</span>
      </button>
    </div>
  );
}

/**
 * Every file on the grant, in the server's order: its name, where it came
 * from and when it arrived (as the card words them), and what the card
 * already knows about it. A plain click on a row picks it for the page; a
 * click with a modifier key, or a screen too narrow to show the card beside
 * the list, opens the file's own page.
 */
export function FileList({
  grantId,
  cards,
  selected,
  onSelect,
  filter = "all",
}: {
  grantId: Id;
  cards: readonly EvidenceCard[];
  selected: Id | null;
  onSelect: OnSelectFile;
  filter?: FileFilter;
}) {
  const shown = new Set(cardsInFilter(cards, filter).map((c) => c.file.id));

  function clickLink(event: MouseEvent<HTMLAnchorElement>, fileId: Id) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (onSelect(fileId)) event.preventDefault();
  }
  function clickRow(event: MouseEvent<HTMLLIElement>) {
    // The name's own link handles a click on it; anywhere else on the row clicks the link.
    if ((event.target as HTMLElement).closest("a, button")) return;
    event.currentTarget.querySelector<HTMLAnchorElement>("a")?.click();
  }

  return (
    <ol className={styles.list} aria-label="Files">
      {cards.map((card) => {
        const { file } = card;
        if (!shown.has(file.id)) return null;
        const isSelected = selected === file.id;
        const tags = fileTags(card);
        return (
          <li key={file.id} className={styles.row} data-selected={isSelected || undefined} onClick={clickRow}>
            <Link
              className={styles.name}
              href={routes.file(grantId, file.id)}
              aria-current={isSelected ? "true" : undefined}
              onClick={(e) => clickLink(e, file.id)}
            >
              {file.name}
            </Link>
            <span className={styles.meta}>
              {SOURCE_LABELS[file.source] ?? file.source} · Arrived {date(file.arrived_at)}
            </span>
            {tags.length > 0 && (
              <span className={styles.tags}>
                {tags.map((t) => (
                  <span key={t.text} className={styles.tag} data-tone={t.tone}>
                    {t.text}
                  </span>
                ))}
              </span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
