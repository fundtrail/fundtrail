import type { GrantSummary } from "@/lib/api";
import Link from "next/link";
import { date, FUNDER_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { grantName } from "./GrantList";

/** Where a grant stands, at the top of its pages: its name, readiness and dates. Counts only, never a percentage. */
export function GrantHeader({ summary }: { summary: GrantSummary }) {
  const { grant } = summary;
  return (
    <header className="ft-panel ft-grant-head">
      <div>
        <p className="ft-caption">
          {grant.award_number && <span className="ft-id">{grant.award_number}</span>}
          {grant.award_number && " · "}
          {FUNDER_LABELS[grant.funder ?? "NSF"] ?? grant.funder}
        </p>
        <h1 className="ft-title">{grantName(summary)}</h1>
        <p className="ft-caption">
          {summary.end_date ? <>Ends {date(summary.end_date)}</> : <>End date not confirmed yet</>}
          {summary.next_closeout && (
            <>
              {" · "}
              {summary.next_closeout.label} {date(summary.next_closeout.date)}
            </>
          )}
        </p>
        <p className="ft-caption">
          <Link className="ft-link" href={routes.terms(grant.id)}>
            Grant terms
          </Link>
          {" · "}
          <Link className="ft-link" href={routes.reusableNotes(grant.id)}>
            Reusable notes
          </Link>
          {" · "}
          <Link className="ft-link" href={routes.ledger(grant.id)}>
            Ledger
          </Link>
        </p>
      </div>
      <div className="ft-ready">
        <span className="ft-ready__count">{summary.charges_ready}</span>
        <span className="ft-ready__of">
          of {summary.charges_total} charges ready for closeout
        </span>
      </div>
    </header>
  );
}
