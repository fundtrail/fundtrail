"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AgentProgressLine } from "@/components/AgentProgress";
import { AppShell } from "@/components/AppShell";
import { Loadable } from "@/components/Loadable";
import { BudgetFigures } from "@/components/BudgetFigures";
import { ProblemBrief, problemRowKey } from "@/components/ProblemList";
import { SampleTimeline } from "@/components/timeline/TimelinePanel";
import { useGrantDisplayName } from "@/lib/grantName";
import {
  useCharges,
  useGrant,
  useProblemList,
  usePings,
  type Bucket,
  type BudgetView,
  type ChargeRow,
  type GrantDetail,
  type GrantNote,
  type GrantSummary,
  type IsoDate,
  type PeriodOfPerformance,
  type ProblemRow,
  type TermView,
} from "@/lib/api";
import { BUCKET_LABELS, date, FUNDER_LABELS, money } from "@/lib/format";
import { routes } from "@/lib/routes";
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

/** A plain share of two amounts, held to a bar's length. */
function share(part: number, whole: number): number {
  if (whole <= 0) return part > 0 ? 100 : 0;
  return Math.min(100, Math.max(0, (part / whole) * 100));
}

/** How many problems, worded for the head of the list. */
function needWords(n: number): string {
  return n === 1 ? "1 thing needs you" : `${n} things need you`;
}

function Head({ summary, start }: { summary: GrantSummary; start: IsoDate | null }) {
  const grantName = useGrantDisplayName();
  const { grant } = summary;
  return (
    <header className={styles.head}>
      <div className={styles.headText}>
        <h1 className={styles.title}>{grantName(summary)}</h1>
        <p className={styles.meta}>
          {grant.award_number && <span className="ft-id">{grant.award_number}</span>}
          <span>{FUNDER_LABELS[grant.funder ?? "NSF"] ?? grant.funder}</span>
          <span className="ft-num">
            {summary.end_date ? (
              start ? (
                <>
                  {date(start)} to {date(summary.end_date)}
                </>
              ) : (
                <>Ends {date(summary.end_date)}</>
              )
            ) : (
              <>End date not confirmed yet</>
            )}
          </span>
        </p>
        {/* Ruling 71: the agent's progress while it reads, or its last run's summary. */}
        <AgentProgressLine summary={summary} />
      </div>
      <Link className="ft-btn" href={routes.closeout(grant.id)}>
        Evidence report
      </Link>
    </header>
  );
}

/**
 * What needs the accountant: the first three rows of the problem list as the
 * server sent them, each opening the problem list with that row picked. Every
 * count here is the number of rows sent; until they arrive, the head shows the
 * grant summary's count.
 */
function NeedsYou({ grantId, summary, rows }: { grantId: string; summary: GrantSummary; rows: ProblemRow[] | undefined }) {
  // On a sample grant the timeline guide's button is the page's filled one, so this one is outlined.
  const main = summary.grant.sample ? "ft-btn" : "ft-btn ft-btn--main";
  const n = rows ? rows.length : summary.on_problem_list;
  const first = (rows ?? []).slice(0, 3);
  if (rows && rows.length === 0) {
    return (
      <section className={`${styles.need} ${styles.needDone}`} aria-labelledby="need-heading">
        <span className={styles.doneMark} aria-hidden="true" />
        <h2 id="need-heading" className={styles.needTitle}>
          Nothing on the problem list.
        </h2>
      </section>
    );
  }
  return (
    <section className={styles.need} aria-labelledby="need-heading">
      <div className={styles.needHead}>
        <h2 id="need-heading" className={styles.needTitle}>
          {needWords(n)}
        </h2>
        <Link className={main} href={routes.problemList(grantId)}>
          Open the problem list
        </Link>
      </div>
      {rows && (
        <div className={styles.needRows}>
          {first.map((row, i) => (
            <ProblemBrief key={problemRowKey(row, i)} row={row} href={routes.problemList(grantId, problemRowKey(row, i))} />
          ))}
        </div>
      )}
      {rows && n > first.length && (
        <div className={styles.needFoot}>
          <span className="ft-num">{n - first.length} more on the problem list</span>
          <Link className="ft-link" href={routes.problemList(grantId)}>
            See all {n}
          </Link>
        </div>
      )}
    </section>
  );
}

const READY_ORDER: Bucket[] = ["evidence_complete", "possible_conflict", "needs_human", "missing_evidence"];

function Ready({ summary }: { summary: GrantSummary }) {
  const counts = summary.bucket_counts;
  const shown = READY_ORDER.filter((b) => (counts?.[b] ?? 0) > 0);
  return (
    <div className={styles.fact}>
      <h2 className={styles.factLabel}>Ready for closeout</h2>
      <p className={styles.big}>
        <span className="ft-num">{summary.charges_ready}</span>{" "}
        <small>of {summary.charges_total} charges</small>
      </p>
      {summary.charges_total > 0 && (
        <div className={styles.meter} aria-hidden="true">
          <i className={styles.ready} style={{ width: `${share(summary.charges_ready, summary.charges_total).toFixed(1)}%` }} />
        </div>
      )}
      {/* The buckets, as the checks gave them: a list of its own, not parts of the bar. */}
      {shown.length > 0 && (
        <ul className={styles.legend} aria-label="Charges by bucket">
          {shown.map((b) => (
            <li key={b} data-bucket={b}>
              <span className="ft-num">{counts[b]}</span> {BUCKET_LABELS[b]}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Charged({ budget, notes }: { budget: BudgetView; notes: GrantNote[] }) {
  const limit = budget.limit_cents;
  return (
    <div className={styles.fact}>
      <h2 className={styles.factLabel}>Charged</h2>
      <p className={styles.big}>
        <span className="ft-num">{money(budget.spent_cents)}</span>
        {limit != null && (
          <>
            {" "}
            <small>of the award&apos;s {money(limit)} limit</small>
          </>
        )}
      </p>
      {limit != null && limit > 0 && (
        <div className={styles.meter} aria-hidden="true">
          <i className={styles.spent} style={{ width: `${share(budget.spent_cents, limit).toFixed(1)}%` }} />
        </div>
      )}
      {notes.length > 0 && (
        <ul className={styles.factNotes} aria-label="Grant notes">
          {notes.map((n, i) => (
            <li key={`${n.check}:${i}`}>{n.text}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The next closeout date and its label as the server gives them, and the grant's today. The period is in the head. */
function NextCloseout({ summary }: { summary: GrantSummary }) {
  const next = summary.next_closeout;
  return (
    <div className={styles.fact}>
      <h2 className={styles.factLabel}>Next closeout date</h2>
      {next && (
        <>
          <p className={styles.big}>
            <span className="ft-num">{date(next.date)}</span>
          </p>
          <p className={styles.factSub}>{next.label}</p>
        </>
      )}
      {summary.now && <p className={`ft-num ${styles.factSub}`}>Today {date(summary.now)}</p>}
    </div>
  );
}

/** Words for the sign-off state, as the closeout page says them. */
const SIGN_OFF_WORDS = {
  not_signed: "Not signed off yet",
  signed: "Signed off",
  changed: "Changed since sign-off",
} as const;

function GrantFile({ grantId, detail, charges }: { grantId: string; detail: GrantDetail; charges: ChargeRow[] | undefined }) {
  const inEffect = detail.terms.filter((t) => t.state === "counts").length;
  const waiting = detail.terms.filter((t) => t.state === "waiting").length;
  const notes = (detail.reusable_notes ?? []).length;
  return (
    <section className={styles.file} aria-labelledby="file-heading">
      <h2 id="file-heading" className={styles.colHeading}>
        The grant&apos;s file
      </h2>
      <ul className={styles.fileRows}>
        <li>
          <span>Grant terms</span>
          <Link className="ft-link ft-num" href={routes.terms(grantId)}>
            {inEffect} in effect · {waiting} waiting
          </Link>
        </li>
        <li>
          <span>Reusable notes</span>
          <Link className="ft-link ft-num" href={routes.reusableNotes(grantId)}>
            {notes} {notes === 1 ? "note" : "notes"}
          </Link>
        </li>
        <li>
          <span>All charges</span>
          <Link className="ft-link ft-num" href={routes.charges(grantId)}>
            {charges ? `${charges.length} ${charges.length === 1 ? "charge" : "charges"}` : "Charges"}
          </Link>
        </li>
        <li>
          <span>Evidence report</span>
          <Link className="ft-link" href={routes.closeout(grantId)}>
            {SIGN_OFF_WORDS[detail.sign_off.state]}
          </Link>
        </li>
      </ul>
    </section>
  );
}

/**
 * A grant's overview: where it stands, with detail one click in. Its name and
 * period, a sample grant's timeline folded to one line, what needs the
 * accountant with the way into the problem list (the one place that lists
 * problems), three facts (ready for closeout, charged with the grant's notes,
 * the next closeout date with the period and today), then the budget and the
 * grant's file. Each part is its own request, so a refetch of one doesn't wait on the
 * others. Every date is the server's, on the grant's own clock.
 */
export function GrantScreen() {
  const grantName = useGrantDisplayName();
  const { grantId } = useParams<{ grantId: string }>();
  // Everything on the page refetches when the backend pings this grant's channel.
  usePings(`grant:${grantId}`);
  const grant = useGrant(grantId);
  const problems = useProblemList(grantId);
  const charges = useCharges(grantId);
  const summary = grant.data?.summary;

  return (
    <AppShell workspaceId={summary?.grant.workspace_id ?? null} crumbs={[summary ? grantName(summary) : "Grant"]}>
      <div className={styles.page}>
        <Loadable result={grant}>
          {(data) => {
            const start = periodStart(data.terms);
            return (
              <>
                <Head summary={data.summary} start={start} />
                {/* Only a sample grant has a timeline to play. */}
                <SampleTimeline summary={data.summary} />
                <NeedsYou grantId={grantId} summary={data.summary} rows={problems.data?.rows} />
                {problems.error && <Loadable result={problems}>{() => null}</Loadable>}
                <div className={styles.facts}>
                  <Ready summary={data.summary} />
                  <Charged budget={data.budget} notes={data.grant_notes} />
                  <NextCloseout summary={data.summary} />
                </div>
                <div className={styles.cols}>
                  <BudgetFigures budget={data.budget} ledgerHref={routes.ledger(grantId)} />
                  <GrantFile grantId={grantId} detail={data} charges={charges.data} />
                </div>
              </>
            );
          }}
        </Loadable>
      </div>
    </AppShell>
  );
}
