"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { useRef } from "react";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { BudgetFigures } from "@/components/BudgetFigures";
import { ChargesTable } from "@/components/ChargesTable";
import disclosure from "@/components/Disclosure.module.css";
import { GrantHeader } from "@/components/GrantHeader";
import { ProblemList, problemRowKey } from "@/components/ProblemList";
import { SampleTimeline } from "@/components/timeline/TimelinePanel";
import { useGrantDisplayName } from "@/lib/grantName";
import { useCharges, useGrant, useProblemList, usePings, type IsoDate, type PeriodOfPerformance, type TermView } from "@/lib/api";
import { SelectedItem } from "./SelectedItem";
import styles from "./grant.module.css";

/**
 * The start of the grant's period: the one period of performance term in
 * force, as the server marks it. Null when there isn't exactly one, or it has
 * no start.
 */
function periodStart(terms: TermView[]): IsoDate | null {
  const inForce = terms.filter((t) => t.state === "counts" && t.record.data.kind === "period_of_performance");
  if (inForce.length !== 1) return null;
  return (inForce[0].record.data as PeriodOfPerformance).start?.value ?? null;
}

/** Under this width the two panes stack, so picking a row scrolls to the item. */
const STACKED = "(max-width: 1100px)";

/**
 * A grant's page: a sample grant's timeline, where the grant stands, its
 * problem list beside the item picked on it, then its budget figures with the
 * grant notes and every charge. Each part is its own request, so a refetch of
 * one doesn't wait on the others. The picked row is the `item` search param,
 * so reload and back keep it; with none, the first row is shown.
 */
export function GrantScreen() {
  const { grantId } = useParams<{ grantId: string }>();
  const grantName = useGrantDisplayName();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const pane = useRef<HTMLElement>(null);
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const charges = useCharges(grantId);
  // Everything on the page refetches when the backend pings this grant's channel.
  usePings(`grant:${grantId}`);
  const summary = grant.data?.summary;

  const rows = problems.data?.rows ?? [];
  const keys = rows.map((r, i) => problemRowKey(r, i));
  const asked = search.get("item");
  // A key that's no longer a row still shows a charge or record by its ID; anything else falls back to the first row.
  const selected = asked && (keys.includes(asked) || /^(charge|record):./.test(asked)) ? asked : (keys[0] ?? null);
  const selectedRow = selected ? (rows[keys.indexOf(selected)] ?? null) : null;

  function select(key: string) {
    const query = new URLSearchParams(search.toString());
    query.set("item", key);
    router.push(`${pathname}?${query.toString()}`, { scroll: false });
    if (typeof window !== "undefined" && window.matchMedia(STACKED).matches) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      pane.current?.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    }
  }

  return (
    <AppShell workspaceId={summary?.grant.workspace_id ?? null} crumbs={[summary ? grantName(summary) : "Grant"]}>
      {/* Only a sample grant has a timeline to play. */}
      {grant.data && <SampleTimeline summary={grant.data.summary} />}

      <Loadable result={grant}>{(data) => <GrantHeader summary={data.summary} start={periodStart(data.terms)} budget={data.budget} />}</Loadable>

      <div className={styles.split} data-single={problems.data && !selected ? "" : undefined}>
        <section id="problem-list" className={`ft-panel ${styles.listPanel}`} aria-labelledby="problems-heading">
          <h2 id="problems-heading" className="ft-sr">
            Problem list
          </h2>
          <Loadable result={problems}>
            {(data) => (
              <ProblemList
                rows={data.rows}
                charges={Object.fromEntries((charges.data ?? []).map((r) => [r.charge.id, r.charge]))}
                selected={selected}
                onSelect={select}
              />
            )}
          </Loadable>
        </section>
        {selected && (
          <section ref={pane} className={styles.pane} aria-label="The selected item">
            <SelectedItem key={selected} grantId={grantId} itemKey={selected} row={selectedRow} />
          </section>
        )}
      </div>

      <Loadable result={grant}>{(data) => <BudgetFigures budget={data.budget} notes={data.grant_notes} />}</Loadable>

      <section className={`ft-panel ${disclosure.panel}`} aria-labelledby="charges-heading">
        <details className={disclosure.details}>
          <summary className={disclosure.summary}>
            <span className={disclosure.chevron} aria-hidden="true" />
            <h2 id="charges-heading" className="ft-heading">
              Charges
            </h2>
            {charges.data && <span className={`ft-count ${disclosure.aside}`}>{charges.data.length}</span>}
          </summary>
          <div className={disclosure.body}>
            <Loadable result={charges}>{(rows) => <ChargesTable rows={rows} />}</Loadable>
          </div>
        </details>
      </section>
    </AppShell>
  );
}
