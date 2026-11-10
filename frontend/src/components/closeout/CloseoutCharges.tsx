"use client";

import Link from "next/link";
import { Fragment, useState } from "react";
import useSWR from "swr";
import { ChargeStatusBadge } from "@/components/BucketBadge";
import {
  useApi,
  type ChargeDetail,
  type ChargeRow,
  type ChargeStatus,
  type Id,
  type LinkView,
  type StatusEntry,
} from "@/lib/api";
import { useUserId } from "@/lib/auth";
import { date, money, recordKindLabel } from "@/lib/format";
import { routes } from "@/lib/routes";

function isChargeStatus(status: StatusEntry["status"]): status is ChargeStatus {
  return "charge_id" in status && "bucket" in status;
}

function linkName(view: LinkView): string {
  return view.file?.name ?? recordKindLabel(view.record.data.kind);
}

/** A charge's evidence and history, loaded from GET /charges/{id} when its row is opened. */
function EvidenceAndHistory({ grantId, chargeId }: { grantId: Id; chargeId: Id }) {
  const api = useApi();
  const userId = useUserId();
  const detail = useSWR<ChargeDetail>(userId ? [userId, "closeout-charge", chargeId] : null, () => api.getCharge(chargeId));

  if (detail.error) {
    return (
      <p className="ft-error" role="alert">
        Couldn&apos;t load this charge&apos;s evidence and history.
      </p>
    );
  }
  if (!detail.data) return <p className="ft-empty">Loading…</p>;
  const links = detail.data.links ?? [];
  const history = detail.data.history ?? [];
  return (
    <div>
      <p className="ft-label">Evidence</p>
      {links.length === 0 ? (
        <p className="ft-caption">No evidence linked.</p>
      ) : (
        <ul>
          {links.map((view) => (
            <li key={view.link.id}>
              {view.file ? (
                <Link className="ft-link" href={routes.file(grantId, view.file.id)}>
                  {linkName(view)}
                </Link>
              ) : (
                linkName(view)
              )}
              {view.link.data.amount_cents != null && <span className="ft-num">, {money(view.link.data.amount_cents)}</span>}
              {view.link.author === "agent" && <span className="ft-caption"> · linked by the agent</span>}
              {view.link.author === "user" && <span className="ft-caption"> · linked by the accountant</span>}
            </li>
          ))}
        </ul>
      )}
      <p className="ft-label">History</p>
      {history.length === 0 ? (
        <p className="ft-caption">No status changes yet.</p>
      ) : (
        <ol>
          {history.map((h, i) => (
            <li key={i}>
              <span className="ft-num">{date(h.entry.changed_at)}</span> · {h.text}
              {isChargeStatus(h.entry.status) && (
                <>
                  {" · "}
                  <ChargeStatusBadge status={h.entry.status} />
                </>
              )}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/**
 * Every expense on the grant (product.md, What the user gets): its bucket, and,
 * when the row is opened, its evidence and its status history. Rows keep the
 * server's order.
 */
export function CloseoutCharges({ grantId, rows }: { grantId: Id; rows: ChargeRow[] }) {
  const [open, setOpen] = useState<Set<Id>>(new Set());
  if (rows.length === 0) return <p className="ft-empty">No charges.</p>;

  function toggle(id: Id) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <table className="ft-ledger ft-ledger--flush">
      <thead>
        <tr>
          <th scope="col">Date</th>
          <th scope="col">Charge</th>
          <th scope="col" className="ft-right">
            Amount
          </th>
          <th scope="col">Bucket</th>
          <th scope="col">Evidence and history</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ charge, status }) => {
          const isOpen = open.has(charge.id);
          return (
            <Fragment key={charge.id}>
              <tr>
                <td>
                  <div className="ft-num">{date(charge.transaction_date)}</div>
                  <div className="ft-id">{charge.ledger_line_id}</div>
                </td>
                <td>
                  <Link className="ft-link" href={routes.charge(grantId, charge.id)}>
                    {charge.description}
                  </Link>
                  {charge.vendor && <div className="ft-caption">{charge.vendor}</div>}
                </td>
                <td className="ft-right ft-num">{money(charge.amount_cents)}</td>
                <td>
                  <ChargeStatusBadge status={status ?? null} />
                </td>
                <td>
                  <button
                    type="button"
                    className="ft-btn ft-btn--sm"
                    aria-expanded={isOpen}
                    aria-controls={isOpen ? `closeout-detail-${charge.id}` : undefined}
                    aria-label={`${isOpen ? "Hide" : "Show"} evidence and history for ${charge.ledger_line_id}`}
                    onClick={() => toggle(charge.id)}
                  >
                    {isOpen ? "Hide" : "Show"}
                  </button>
                </td>
              </tr>
              {isOpen && (
                <tr id={`closeout-detail-${charge.id}`} aria-label={`Evidence and history for ${charge.ledger_line_id}`}>
                  <td colSpan={5}>
                    <EvidenceAndHistory grantId={grantId} chargeId={charge.id} />
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}
