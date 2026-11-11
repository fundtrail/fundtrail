import Link from "next/link";
import type { LinkView } from "@/lib/api";
import { date, money, recordKindLabel } from "@/lib/format";
import { citedValue, field } from "./labels";
import { TrailGroup, TrailNode, TrailNote } from "./Trail";

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
 * the evidence trail, with how much of each bill it uses. Each name opens the
 * viewer at the link's part. A link with values still unconfirmed shows its
 * detail; the rest are single lines that open in place.
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
        // A long statement or approval scope reads as detail, not as a status.
        const shortWhat = what && what.length <= 28 ? what : null;
        return (
          <TrailNode
            key={view.link.id}
            mark="holds"
            open={unconfirmed.length > 0}
            title={
              href ? (
                <Link className="ft-link" href={href}>
                  {name}
                </Link>
              ) : (
                <span className="ft-strong">{name}</span>
              )
            }
            status={shortWhat && <span className="ft-num">{shortWhat}</span>}
            sub={
              <>
                {recordKindLabel(view.record.data.kind)}
                {from && <> · {from}</>}
              </>
            }
          >
            {what && !shortWhat && <p className="ft-num">{what}</p>}
            {reason && (
              <p>
                <span className="ft-label">{view.link.author === "agent" ? "Agent's reason: " : "Accountant's reason: "}</span>
                {reason}
              </p>
            )}
            <p className="ft-caption">
              Linked by {view.link.author === "agent" ? "the agent" : "the accountant"}, {date(view.link.written_at)}
              {unconfirmed.length > 0 && <> · Not confirmed: {unconfirmed.join(", ")}</>}
            </p>
          </TrailNode>
        );
      })}
    </TrailGroup>
  );
}
