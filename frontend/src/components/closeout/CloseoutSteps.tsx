import type { CSSProperties, ReactNode } from "react";
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

type Mark = "past" | "now" | "ahead" | "plain";

interface TrailNode {
  key: string;
  mark: Mark;
  date: string | null;
  name: string;
  when: string | null;
}

/**
 * Which step the server's next closeout date names: the step whose name its
 * label carries ("Final financial report due" names "Final financial report").
 * -1 when the server sends none, or names a step this list doesn't show.
 */
function nextStepIndex(summary: GrantSummary): number {
  const label = summary.next_closeout?.label.toLowerCase();
  if (!label) return -1;
  return BERKELEY_STEPS.findIndex((s) => label.includes(s.name.toLowerCase()));
}

/**
 * The trail's nodes. Dates come only from the server: the end date in force
 * under "End date", the next closeout date under the step it names, and the
 * grant's now (ruling 40) where it falls, just before that step. With no next
 * step named, every step is drawn the same.
 */
function nodes(summary: GrantSummary): TrailNode[] {
  const next = nextStepIndex(summary);
  const out: TrailNode[] = [];
  BERKELEY_STEPS.forEach((s, i) => {
    if (i === next) {
      out.push({ key: "now", mark: "now", date: date(summary.now), name: "Now", when: null });
    }
    let dated: string | null = null;
    if (i === next && summary.next_closeout) dated = date(summary.next_closeout.date);
    else if (s.name === "End date" && summary.end_date) dated = date(summary.end_date);
    out.push({ key: s.name, mark: next < 0 ? "plain" : i < next ? "past" : "ahead", date: dated, name: s.name, when: s.when });
  });
  return out;
}

/** The line after a node runs solid up to now, dashed ahead of it. */
function lineAfter(list: TrailNode[], i: number): "solid" | "dashed" | "plain" {
  const following = list[i + 1];
  if (!following || following.mark === "plain") return "plain";
  return following.mark === "ahead" ? "dashed" : "solid";
}

export function CloseoutSteps({ summary, links }: { summary: GrantSummary; links?: ReactNode }) {
  const list = nodes(summary);
  return (
    <section className="ft-panel ft-co-steps-panel" aria-labelledby="steps-heading">
      <div className="ft-panel__head">
        <h2 id="steps-heading" className="ft-heading">
          Closeout steps
        </h2>
        {links}
      </div>
      <div className="ft-co-body">
        <p className="ft-co-summary">
          {summary.end_date ? <>End date in force: {date(summary.end_date)}.</> : <>End date not confirmed yet.</>}
          {summary.next_closeout && (
            <>
              {" "}
              Next: <span className="ft-strong">{summary.next_closeout.label}</span>, {date(summary.next_closeout.date)}.
            </>
          )}
        </p>
        <ol
          className="ft-co-steps"
          style={{ "--co-cols": list.map((n) => (n.mark === "now" ? "minmax(88px, 0.6fr)" : "minmax(0, 1fr)")).join(" ") } as CSSProperties}
        >
          {list.map((n, i) => (
            <li
              key={n.key}
              className={`ft-co-step is-${n.mark}`}
              data-line={lineAfter(list, i)}
              aria-current={n.mark === "now" ? "step" : undefined}
            >
              <span className="ft-co-step__dot" aria-hidden="true" />
              {n.date && <span className="ft-co-step__date">{n.date}</span>}
              <span className="ft-co-step__name">{n.name}</span>
              {n.when && <span>{n.when}</span>}
            </li>
          ))}
        </ol>
        <p className="ft-caption">Berkeley&apos;s steps, the first set. Dates that depend on the university&apos;s own calendar aren&apos;t worked out.</p>
      </div>
    </section>
  );
}
