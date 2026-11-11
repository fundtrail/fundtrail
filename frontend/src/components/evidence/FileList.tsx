"use client";

import Link from "next/link";
import type { MouseEvent } from "react";
import type { EvidenceCard, Id } from "@/lib/api";
import { date, SOURCE_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { duplicateWords, STATE_WORDS } from "./EvidenceCardView";
import styles from "./FileList.module.css";

/**
 * Picks a file for the page to show beside the list. Returning false lets the
 * row's link open the file's own page instead (a screen too narrow for both).
 */
export type OnSelectFile = (fileId: Id) => boolean;

/**
 * What the card already says about a file, in the card's own words and under
 * the card's own conditions: a fact waiting for the accountant, a value that
 * isn't confirmed, and a copy of another file (with the copy mark's state, as
 * the card writes it). Nothing here is worked out beyond what the card shows.
 */
export function fileTags(card: EvidenceCard): { text: string; tone: "waiting" | "quiet" }[] {
  const facts = card.facts ?? [];
  const tags: { text: string; tone: "waiting" | "quiet" }[] = [];
  if (facts.some((f) => f.state === "waiting")) tags.push({ text: STATE_WORDS.waiting ?? "Waiting for the accountant", tone: "waiting" });
  if (facts.some((f) => (f.values ?? []).some((v) => !v.confirmed))) tags.push({ text: "Unconfirmed", tone: "quiet" });
  const copy = duplicateWords(card);
  if (copy) tags.push({ text: copy, tone: "quiet" });
  return tags;
}

/**
 * Every file on the grant, in the server's order: its name, where it came
 * from and when it arrived (as the card words them), and what the card
 * already says about it. A plain click on a row picks it for the page; a
 * click with a modifier key, or a screen too narrow to show the card beside
 * the list, opens the file's own page.
 */
export function FileList({
  grantId,
  cards,
  selected,
  onSelect,
}: {
  grantId: Id;
  cards: readonly EvidenceCard[];
  selected: Id | null;
  onSelect: OnSelectFile;
}) {
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
