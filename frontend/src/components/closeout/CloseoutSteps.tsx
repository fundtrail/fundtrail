import type { GrantSummary } from "@/lib/api";
import { date } from "@/lib/format";

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

export function CloseoutSteps({ summary }: { summary: GrantSummary }) {
  return (
    <section className="ft-panel" aria-labelledby="steps-heading">
      <div className="ft-panel__head">
        <h2 id="steps-heading" className="ft-heading">
          Closeout steps
        </h2>
      </div>
      <p>
        {summary.end_date ? <>End date in force: {date(summary.end_date)}.</> : <>End date not confirmed yet.</>}
        {summary.next_closeout && (
          <>
            {" "}
            Next: <span className="ft-strong">{summary.next_closeout.label}</span>, {date(summary.next_closeout.date)}.
          </>
        )}
      </p>
      <ol>
        {BERKELEY_STEPS.map((s) => (
          <li key={s.name}>
            <span className="ft-strong">{s.name}.</span> <span className="ft-caption">{s.when}</span>
          </li>
        ))}
      </ol>
      <p className="ft-caption">Berkeley&apos;s steps, the first set. Dates that depend on the university&apos;s own calendar aren&apos;t worked out.</p>
    </section>
  );
}
