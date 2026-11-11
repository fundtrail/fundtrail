"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { ProblemFilters, ProblemList, problemRowKey, type ProblemFilter } from "@/components/ProblemList";
import { SelectedProblem } from "@/components/SelectedProblem";
import { useGrantDisplayName } from "@/lib/grantName";
import { useCharges, useGrant, usePings, useProblemList } from "@/lib/api";
import { routes } from "@/lib/routes";
import styles from "./problems.module.css";

/** Under this width the list is the page, and a row opens its own page. */
const NARROW = "(max-width: 980px)";

/**
 * The problem list: every row the server sent, in its order, beside the one
 * picked. The pick is the `item` search param, so reload and back keep it;
 * with none, the first row is shown. On a narrow screen the list is the page
 * and a row opens its own page.
 */
export function ProblemsScreen() {
  const grantName = useGrantDisplayName();
  const { grantId } = useParams<{ grantId: string }>();
  // Everything on the page refetches when the backend pings this grant's channel.
  usePings(`grant:${grantId}`);
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const charges = useCharges(grantId);
  const [filter, setFilter] = useState<ProblemFilter>("all");
  const summary = grant.data?.summary;

  const rows = problems.data?.rows ?? [];
  const keys = rows.map((r, i) => problemRowKey(r, i));
  const asked = search.get("item");
  // A key that's no longer a row still shows a charge or record by its ID; anything else falls back to the first row.
  const selected = asked && (keys.includes(asked) || /^(charge|record):./.test(asked)) ? asked : (keys[0] ?? null);
  const selectedRow = selected ? (rows[keys.indexOf(selected)] ?? null) : null;

  function select(key: string): boolean {
    // Too narrow to show the item beside the list: the row's link opens its own page.
    if (window.matchMedia(NARROW).matches) return false;
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
                    selected={selected}
                    onSelect={select}
                    reasons="first"
                    variant="narrow"
                    filter={filter}
                    onFilter={setFilter}
                    tabs={false}
                  />
                </section>
                {selected && (
                  <section className={styles.detail} aria-label="The selected item">
                    <SelectedProblem key={selected} grantId={grantId} itemKey={selected} row={selectedRow} />
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
