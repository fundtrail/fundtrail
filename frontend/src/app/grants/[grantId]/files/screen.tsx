"use client";

import Link from "next/link";
import { useGrant, usePings } from "@/lib/api";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import { Loadable } from "@/components/Loadable";
import { EvidenceCardView } from "@/components/evidence/EvidenceCardView";
import { FileList } from "@/components/evidence/FileList";
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
 * reload and back keep it; with none, the first file is shown, and one that
 * isn't on the grant is replaced in the address (no new history entry) by the
 * file shown, so the address stays true. On a narrow screen the list is the
 * page: a row opens the file's own page (the viewer), and a link with `file`
 * goes straight there.
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
  const summary = grant.data?.summary;

  const cards = evidence.data ?? [];
  const asked = search.get("file");
  const askedIsKnown = asked !== null && cards.some((c) => c.file.id === asked);
  const selected = askedIsKnown ? asked : (cards[0]?.file.id ?? null);
  const selectedCard = cards.find((c) => c.file.id === selected) ?? null;

  // Arriving on a narrow screen with a file asked for opens that file's own page.
  // Only on arrival: narrowing the window later doesn't navigate away.
  const askedHref = asked && askedIsKnown ? routes.file(grantId, asked) : null;
  useEffect(() => {
    if (askedHref && isNarrow()) router.replace(askedHref);
  }, [askedHref, router]);

  // A file the address names that isn't on the grant: once the files are in,
  // the address is replaced, without a new history entry, by the file shown
  // (or by none on a narrow screen, where no file is shown beside the list).
  const unknownAsked = asked !== null && evidence.data !== undefined && !askedIsKnown;
  const shownInstead = unknownAsked && !narrow ? selected : null;
  const searchString = search.toString();
  useEffect(() => {
    if (!unknownAsked) return;
    const query = new URLSearchParams(searchString);
    if (shownInstead) query.set("file", shownInstead);
    else query.delete("file");
    const rest = query.toString();
    router.replace(rest ? `${pathname}?${rest}` : pathname, { scroll: false });
  }, [unknownAsked, shownInstead, searchString, pathname, router]);

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
              <h1 className={`ft-title ${styles.title}`}>Evidence</h1>
              {evidence.data && (
                <span className={styles.fileCount}>
                  {cards.length} {cards.length === 1 ? "file" : "files"}
                </span>
              )}
            </div>
          </div>
        </header>
        <Loadable result={evidence} onRetry={() => void evidence.mutate()}>
          {(data) =>
            data.length === 0 ? (
              <p className={styles.empty}>No evidence on this grant yet.</p>
            ) : (
              <div className={styles.split}>
                {/* The list itself carries the name "Files"; its box is only layout. */}
                <div className={styles.listBox}>
                  <FileList grantId={grantId} cards={data} selected={narrow ? null : selected} onSelect={select} />
                </div>
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
