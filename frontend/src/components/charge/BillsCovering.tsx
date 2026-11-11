import Link from "next/link";
import type { LinkView } from "@/lib/api";
import { date, money, recordKindLabel } from "@/lib/format";
import { citedValue, field } from "./labels";
import { TrailGroup, TrailNode, TrailNote } from "./Trail";
import styles from "./charge.module.css";

/** One line on what the linked record gives: "$5,000.00 of $10,000.00" for a bill. */
function uses(view: LinkView): string | null {
  const amount = field<number | null>(view.link, "amount_cents");
  const kind = view.record.data.kind;
  if (kind === "bill") {
    const total = citedValue<number>(view.record, "total");
    if (amount === null || amount === undefined) return total === undefined ? null : `Bill total ${money(total)}`;
    return total === undefined ? money(amount) : `${money(amount)} of ${money(total)}`;
  }
  if (kind === "approval") return citedValue<string>(view.record, "covers") ?? null;
  if (kind === "note") return citedValue<string>(view.record, "statement") ?? null;
  return amount === null || amount === undefined ? null : money(amount);
}

function source(view: LinkView): string | null {
  const kind = view.record.data.kind;
  if (kind === "bill") return citedValue<string>(view.record, "vendor") ?? citedValue<string>(view.record, "document_number") ?? null;
  if (kind === "approval") return citedValue<string>(view.record, "approver_name") ?? citedValue<string>(view.record, "approver_email") ?? null;
  if (kind === "note") return field<string>(view.record, "label") ?? null;
  return null;
}

/**
 * The bills, approvals and explaining notes linked to the charge, as nodes on
 * the evidence trail. How much of each bill the charge uses is always on the
 * bill's line; what an approval covers or a note states is always under it.
 * Each name opens the viewer at the link's part.
 *
 * A link holds (a check, the line solid) only when every value it rests on is
 * confirmed. A link with values not yet confirmed can't make anything pass:
 * it gets the needs-a-human ring, the line turns dashed from it, and its
 * unconfirmed values are named on the line.
 */
export function BillsCovering({ links, viewerHref }: { links: LinkView[]; viewerHref?: (view: LinkView) => string | undefined }) {
  return (
    <TrailGroup label="Bills and evidence covering this charge">
      {links.length === 0 && <TrailNote>Nothing is linked to this charge yet.</TrailNote>}
      {links.map((view) => {
        const name = view.file?.name ?? `${recordKindLabel(view.record.data.kind)} typed by the accountant`;
        const href = viewerHref?.(view);
        const unconfirmed = (view.values ?? []).filter((v) => !v.confirmed).map((v) => v.path);
        const reason = field<string | null>(view.link, "reason");
        const what = uses(view);
        const from = source(view);
        const isBill = view.record.data.kind === "bill";
        const holds = unconfirmed.length === 0;
        return (
          <TrailNode
            key={view.link.id}
            testId="link"
            mark={holds ? "holds" : "human"}
            broken={!holds}
            open={!holds}
            toggleLabel={href ? `Details, ${name}` : undefined}
            title={
              href ? (
                <Link className="ft-link" href={href}>
                  {name}
                </Link>
              ) : (
                <span className="ft-strong">{name}</span>
              )
            }
            status={what && isBill ? <span className="ft-num">{what}</span> : undefined}
            sub={
              <>
                <p>
                  {recordKindLabel(view.record.data.kind)}
                  {from && <> · {from}</>}
                </p>
                {what && !isBill && <p className={styles.uses}>{what}</p>}
                {!holds && <p className={styles.waitingWord}>Not confirmed: {unconfirmed.join(", ")}</p>}
              </>
            }
          >
            {reason && (
              <p>
                <span className="ft-label">{view.link.author === "agent" ? "Agent's reason: " : "Accountant's reason: "}</span>
                {reason}
              </p>
            )}
            <p className="ft-caption">
              Linked by {view.link.author === "agent" ? "the agent" : "the accountant"}, {date(view.link.written_at)}
            </p>
          </TrailNode>
        );
      })}
    </TrailGroup>
  );
}
