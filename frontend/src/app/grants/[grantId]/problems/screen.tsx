"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { ProblemFilters, ProblemList, problemRowHref, problemRowKey, rowsInFilter, type ProblemFilter } from "@/components/ProblemList";
import { SelectedProblem } from "@/components/SelectedProblem";
import { useGrantDisplayName } from "@/lib/grantName";
import { useCharges, useGrant, usePings, useProblemList } from "@/lib/api";
import { routes } from "@/lib/routes";
import styles from "./problems.module.css";

/** Under this width the list is the page, and a row opens its own page. */
const NARROW = "(max-width: 980px)";

/** Whether the screen is too narrow to show the item beside the list. */
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
 * The problem list: every row the server sent, in its order, beside the one
 * picked. The pick is the `item` search param, so reload and back keep it;
 * with none, or one that's no longer on the list, the first row is shown, and
 * a filter that hides the picked row shows its first row instead. A problem on
 * the grant itself has no page of its own, so on a narrow screen it opens
 * above the list. On a narrow
 * screen the list is the page: a row opens its own page, and a link with
 * `item` goes straight to that item's page.
 */
export function ProblemsScreen() {
  const grantName = useGrantDisplayName();
  const { grantId } = useParams<{ grantId: string }>();
  // Everything on the page refetches when the backend pings this grant's channel.
  usePings(`grant:${grantId}`);
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const narrow = useNarrow();
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const charges = useCharges(grantId);
  const [filter, setFilter] = useState<ProblemFilter>("all");
  const summary = grant.data?.summary;

  const rows = problems.data?.rows ?? [];
  const keys = rows.map((r, i) => problemRowKey(r, i));
  const asked = search.get("item");
  // A benefit charge waiting on its salary line isn't a row of its own, but it is a charge on the grant.
  const askedCharge = asked?.startsWith("charge:") ? (charges.data ?? []).find((r) => `charge:${r.charge.id}` === asked) : undefined;
  const askedIsKnown = asked !== null && (keys.includes(asked) || askedCharge !== undefined);
  const visible = rowsInFilter(rows, filter);
  const visibleKeys = keys.filter((_, i) => visible.includes(rows[i]));
  let selected = askedIsKnown ? asked : (keys[0] ?? null);
  // A filter never hides the picked row while it's shown: the first row the filter shows takes its place.
  if (selected && visible.length < rows.length && !visibleKeys.includes(selected)) selected = visibleKeys[0] ?? null;
  const selectedRow = selected ? (rows[keys.indexOf(selected)] ?? null) : null;

  // Arriving on a narrow screen with one item asked for opens that item's own page.
  // Only on arrival: narrowing the window later doesn't navigate away.
  const askedHref = asked && askedIsKnown ? (askedCharge ? routes.charge(grantId, askedCharge.charge.id) : problemRowHref(rows[keys.indexOf(asked)])) : null;
  useEffect(() => {
    if (askedHref && isNarrow()) router.replace(askedHref);
  }, [askedHref, router]);

  function select(key: string): boolean {
    // Too narrow to show the item beside the list: the row's link opens its own page.
    // A problem on the grant itself has no page of its own, so it opens here, above the list.
    const row = rows[keys.indexOf(key)];
    if (isNarrow() && !(row && row.kind === "grant")) return false;
    const query = new URLSearchParams(search.toString());
    query.set("item", key);
    router.push(`${pathname}?${query.toString()}`, { scroll: false });
    return true;
  }

  return (
    <AppShell workspaceId={summary?.grant.workspace_id ?? null} crumbs={[summary ? grantName(summary) : "Grant", "Problem list"]}>
      <div className={styles.page}>
        <header className={styles.head}>
          <div>
            {summary && (
              <Link className={styles.crumb} href={routes.grant(grantId)}>
                {grantName(summary)}
              </Link>
            )}
            <h1 className={styles.title}>Problem list</h1>
          </div>
          {rows.length > 0 && <ProblemFilters rows={rows} value={filter} onChange={setFilter} look="pills" />}
        </header>
        <Loadable result={problems}>
          {(data) =>
            data.rows.length === 0 ? (
              <div className={styles.empty}>
                <span className={styles.doneMark} aria-hidden="true" />
                <p>Nothing on the problem list.</p>
              </div>
            ) : (
              <div className={styles.split}>
                <section className={styles.list} aria-label="Problem list">
                  <ProblemList
                    rows={data.rows}
                    charges={Object.fromEntries((charges.data ?? []).map((r) => [r.charge.id, r.charge]))}
                    selected={narrow ? null : selected}
                    onSelect={select}
                    variant="pick"
                    filter={filter}
                    onFilter={setFilter}
                  />
                </section>
                {/* Only a screen wide enough to show the item loads it. */}
                {selected && (!narrow || (asked === selected && selectedRow?.kind === "grant")) && (
                  <section className={`${styles.detail}${narrow ? ` ${styles.detailFirst}` : ""}`} aria-label="The selected item">
                    <SelectedProblem key={selected} grantId={grantId} itemKey={selected} row={selectedRow} focusHeading={narrow} />
                  </section>
                )}
              </div>
            )
          }
        </Loadable>
      </div>
    </AppShell>
  );
}
