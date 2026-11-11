"use client";

import Link from "next/link";
import { Fragment, useId, useState } from "react";
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
import "./closeout.css";

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
    <div className="ft-co-evidence">
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
  const col = useId();
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
    // Explicit table roles and header links: at phone width the rows are laid out
    // as blocks, which can drop a table's native semantics in some browsers.
    <table className="ft-ledger ft-co-table" role="table">
      <thead role="rowgroup">
        <tr role="row">
          <th scope="col" role="columnheader" id={`${col}-date`}>
            Date
          </th>
          <th scope="col" role="columnheader" id={`${col}-charge`}>
            Charge
          </th>
          <th scope="col" role="columnheader" id={`${col}-amount`} className="ft-right">
            Amount
          </th>
          <th scope="col" role="columnheader" id={`${col}-bucket`}>
            Bucket
          </th>
          <th scope="col" role="columnheader" id={`${col}-show`}>
            Evidence and history
          </th>
        </tr>
      </thead>
      <tbody role="rowgroup">
        {rows.map(({ charge, status }) => {
          const isOpen = open.has(charge.id);
          return (
            <Fragment key={charge.id}>
              <tr role="row">
                <td role="cell" headers={`${col}-date`} className="ft-co-date">
                  <div className="ft-num">{date(charge.transaction_date)}</div>
                  <div className="ft-id">{charge.ledger_line_id}</div>
                </td>
                <td role="cell" headers={`${col}-charge`}>
                  <Link className="ft-link" href={routes.charge(grantId, charge.id)}>
                    {charge.description}
                  </Link>
                  {charge.vendor && <div className="ft-caption">{charge.vendor}</div>}
                </td>
                <td role="cell" headers={`${col}-amount`} className="ft-right ft-co-amount">
                  {money(charge.amount_cents)}
                </td>
                <td role="cell" headers={`${col}-bucket`}>
                  <ChargeStatusBadge status={status ?? null} />
                </td>
                <td role="cell" headers={`${col}-show`}>
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
                <tr
                  role="row"
                  id={`closeout-detail-${charge.id}`}
                  className="ft-co-detail"
                  aria-label={`Evidence and history for ${charge.ledger_line_id}`}>
                  <td role="cell" colSpan={5}>
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
