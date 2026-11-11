import type { ReactNode } from "react";
import type { GrantSummary } from "@/lib/api";
import { date } from "@/lib/format";
import "./closeout.css";

/**
 * Berkeley's closeout steps in order (product.md, Closeout), the first set.
 * Each step is described relative to the end date, as the docs word it. The
 * screen works out no deadline: it shows the end date in force and the next
 * closeout date the server sends.
 */
const BERKELEY_STEPS: { name: string; when: string }[] = [
  { name: "Notice of Expiration", when: "90 days before the end date. The university asks for a review of every charge." },
  { name: "End date", when: "The last day of the period of performance." },
  {
    name: "Adjustment period",
    when: "From the end date until the books close two months later. Problem charges are moved off the grant, each with a written explanation.",
  },
  {
    name: "Award Closeout Certification",
    when: "Due at the close of the 2nd month. Your form, with the ledger report and the evidence report attached; your supervisor approves it.",
  },
  { name: "Final financial report", when: "Filed by central accounting by day 90. FundTrail isn't involved." },
];

/**
 * The steps as one trail, every step drawn the same: the server says what's
 * next, not where the grant stands among these steps, so the trail marks no
 * step as passed or current. The only date under a step is the end date in
 * force, under End date. What's next leads, in the server's own words.
 */
export function CloseoutSteps({ summary, links }: { summary: GrantSummary; links?: ReactNode }) {
  const next = summary.next_closeout ?? null;
  return (
    <section className="ft-panel ft-co-steps-panel" aria-labelledby="steps-heading">
      <div className="ft-panel__head">
        <h2 id="steps-heading" className="ft-heading">
          Closeout steps
        </h2>
        {links}
      </div>
      <div className="ft-co-body">
        <div className="ft-co-summary" data-testid="closeout-summary">
          {next && (
            <p className="ft-co-next">
              Next: <span className="ft-co-next__label">{next.label}</span>, {date(next.date)}.
            </p>
          )}
          <p className="ft-co-end">
            {summary.end_date ? <>End date in force: {date(summary.end_date)}.</> : <>End date not confirmed yet.</>}
          </p>
        </div>
        <ol className="ft-co-steps">
          {BERKELEY_STEPS.map((s) => (
            <li key={s.name} className="ft-co-step">
              <span className="ft-co-step__dot" aria-hidden="true" />
              {s.name === "End date" && summary.end_date && (
                <span className="ft-co-step__date">{date(summary.end_date)}</span>
              )}
              <span className="ft-co-step__name">{s.name}</span>
              <span className="ft-co-step__when">{s.when}</span>
            </li>
          ))}
        </ol>
        <p className="ft-caption">Berkeley&apos;s steps, the first set. Dates that depend on the university&apos;s own calendar aren&apos;t worked out.</p>
      </div>
    </section>
  );
}
