"use client";

import Link from "next/link";
import { useGrant, usePings } from "@/lib/api";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Loadable } from "@/components/Loadable";
import { EvidenceCardView } from "@/components/evidence/EvidenceCardView";
import { cardsInFilter, FileFilters, FileList, type FileFilter } from "@/components/evidence/FileList";
import styles from "@/components/evidence/FileList.module.css";
import { GrantFrame } from "@/components/evidence/GrantFrame";
import { useEvidence } from "@/components/evidence/hooks";
import { useGrantDisplayName } from "@/lib/grantName";
import { routes } from "@/lib/routes";

/** Under this width the list is the page, and a row opens the file's own page. */
const NARROW = "(max-width: 980px)";

/** Whether the screen is too narrow to show the card beside the list. */
function isNarrow(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(NARROW).matches;
}

function useNarrow(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      if (typeof window.matchMedia !== "function") return () => {};
      const query = window.matchMedia(NARROW);
      query.addEventListener("change", onChange);
      return () => query.removeEventListener("change", onChange);
    },
    isNarrow,
    () => false,
  );
}

/**
 * The grant's evidence: every file, in the server's order, beside the one
 * picked, shown as its evidence card. The pick is the `file` search param, so
 * reload and back keep it; with none, or one that isn't on the grant, the
 * first file is shown, and a filter that hides the picked file shows its first
 * row instead. On a narrow screen the list is the page: a row opens the file's
 * own page (the viewer), and a link with `file` goes straight there.
 */
export function EvidenceScreen() {
  const grantName = useGrantDisplayName();
  const { grantId } = useParams<{ grantId: string }>();
  // Refetches when the backend pings this grant's channel, such as the agent replying in a thread.
  usePings(`grant:${grantId}`);
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const narrow = useNarrow();
  const grant = useGrant(grantId);
  const evidence = useEvidence(grantId);
  const [filter, setFilter] = useState<FileFilter>("all");
  const summary = grant.data?.summary;

  const cards = evidence.data ?? [];
  const asked = search.get("file");
  const askedIsKnown = asked !== null && cards.some((c) => c.file.id === asked);
  const visible = cardsInFilter(cards, filter);
  let selected = askedIsKnown ? asked : (cards[0]?.file.id ?? null);
  // A filter never hides the picked file while its card is shown: the first file the filter shows takes its place.
  if (selected && !visible.some((c) => c.file.id === selected)) selected = visible[0]?.file.id ?? null;
  const selectedCard = cards.find((c) => c.file.id === selected) ?? null;

  // Arriving on a narrow screen with a file asked for opens that file's own page.
  // Only on arrival: narrowing the window later doesn't navigate away.
  const askedHref = asked && askedIsKnown ? routes.file(grantId, asked) : null;
  useEffect(() => {
    if (askedHref && isNarrow()) router.replace(askedHref);
  }, [askedHref, router]);

  function select(fileId: string): boolean {
    // Too narrow to show the card beside the list: the row's link opens the file's page.
    if (isNarrow()) return false;
    const query = new URLSearchParams(search.toString());
    query.set("file", fileId);
    router.push(`${pathname}?${query.toString()}`, { scroll: false });
    return true;
  }

  return (
    <GrantFrame grantId={grantId} crumbs={["Evidence"]}>
      <div className={styles.page}>
        <header className={styles.head}>
          <div>
            {summary && (
              <Link className={styles.crumb} href={routes.grant(grantId)}>
                {grantName(summary)}
              </Link>
            )}
            <div className={styles.titleRow}>
              <h1 className={styles.title}>Evidence</h1>
              {evidence.data && (
                <span className={styles.fileCount}>
                  {cards.length} {cards.length === 1 ? "file" : "files"}
                </span>
              )}
            </div>
          </div>
          {cards.length > 0 && <FileFilters cards={cards} value={filter} onChange={setFilter} />}
        </header>
        <Loadable result={evidence}>
          {(data) =>
            data.length === 0 ? (
              <p className={styles.empty}>No evidence on this grant yet.</p>
            ) : (
              <div className={styles.split}>
                <section className={styles.listBox} aria-label="Files">
                  <FileList grantId={grantId} cards={data} selected={narrow ? null : selected} onSelect={select} filter={filter} />
                </section>
                {/* Only a screen wide enough to show the card loads it. */}
                {!narrow && selectedCard && (
                  <section className={styles.detail} aria-label="The selected file">
                    <div className={styles.paneBar}>
                      <Link className="ft-link" href={routes.file(grantId, selectedCard.file.id)}>
                        Open the file
                      </Link>
                    </div>
                    <EvidenceCardView key={selectedCard.file.id} grantId={grantId} card={selectedCard} headingLevel={2} />
                  </section>
                )}
              </div>
            )
          }
        </Loadable>
      </div>
    </GrantFrame>
  );
}
