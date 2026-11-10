import Link from "next/link";
import type { FtRecord, ProblemRow, Reason } from "@/lib/api";
import { date, HOLD_REASON_LABELS, money, recordKindLabel, SOURCE_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { ChargeStatusBadge } from "./BucketBadge";


/** A reason's text as the server sends it, with when a missing item is expected and whether it was accepted. */
function ReasonLine({ reason }: { reason: Reason }) {
  return (
    <p className="ft-problem__text">
      {reason.text}
      {reason.expected_by && <span className="ft-caption"> · Expected by {date(reason.expected_by)}</span>}
      {reason.accepted_by && (
        <>
          {" "}
          <span className="ft-tag">Accepted</span>
        </>
      )}
    </p>
  );
}

function recordName(record: FtRecord): string {
  return `${recordKindLabel(record.data.kind)}, written ${date(record.written_at)}`;
}

/** The reasons a charge is on the list: every reason that isn't a pass, in the server's order and words. */
function failing(reasons: Reason[]): Reason[] {
  return reasons.filter((r) => r.bucket !== "evidence_complete");
}

function rowKey(row: ProblemRow, index: number): string {
  switch (row.kind) {
    case "grant":
      return `grant:${row.problem.check}:${row.problem.problem}`;
    case "terms_waiting":
      return `terms:${row.file.id}`;
    case "record":
      return `record:${row.status.record_id ?? row.status.file_id ?? index}`;
    case "charge":
      return `charge:${row.charge.id}`;
    case "held_mail":
      return `held_mail:${row.held.id}`;
  }
}

function Row({ row }: { row: ProblemRow }) {
  switch (row.kind) {
    case "grant":
      return (
        <>
          <div className="ft-problem__what">
            <span className="ft-tag">Grant</span>
          </div>
          <div className="ft-problem__main">
            <p className="ft-problem__text">{row.problem.text}</p>
          </div>
          <div className="ft-problem__side">
            {row.problem.accepted && <span className="ft-tag">Accepted</span>}
            {row.problem.snoozed && <span className="ft-tag">Snoozed</span>}
          </div>
        </>
      );
    case "terms_waiting":
      return (
        <>
          <div className="ft-problem__what">
            <span className="ft-tag">Terms</span>
          </div>
          <div className="ft-problem__main">
            <p className="ft-problem__name">
              <Link className="ft-link" href={routes.terms(row.file.grant_id)}>
                {row.file.name}
              </Link>
            </p>
            <p className="ft-problem__text">{row.text}</p>
          </div>
          <div className="ft-problem__side ft-caption">
            {SOURCE_LABELS[row.file.source]} · {date(row.file.arrived_at)}
          </div>
        </>
      );
    case "record":
      return (
        <>
          <div className="ft-problem__what">
            <span className="ft-tag">{row.file && !row.record ? "File" : "Record"}</span>
          </div>
          <div className="ft-problem__main">
            {row.record ? (
              <p className="ft-problem__name">
                <Link className="ft-link" href={routes.record(row.status.grant_id, row.record.id)}>
                  {row.file ? row.file.name : recordName(row.record)}
                </Link>
              </p>
            ) : (
              row.file && (
                <p className="ft-problem__name">
                  <Link className="ft-link" href={routes.file(row.status.grant_id, row.file.id)}>
                    {row.file.name}
                  </Link>
                </p>
              )
            )}
            {row.status.problems.map((p) => (
              <p className="ft-problem__text" key={`${p.check}:${p.problem}`}>
                {p.text}
              </p>
            ))}
          </div>
          <div className="ft-problem__side">
            {row.status.accepted && <span className="ft-tag">Accepted</span>}
            {row.status.snoozed && <span className="ft-tag">Snoozed</span>}
          </div>
        </>
      );
    case "charge":
      return (
        <>
          <div className="ft-problem__what">
            <span className="ft-num">{date(row.charge.transaction_date)}</span>
            <span className="ft-id">{row.charge.ledger_line_id}</span>
          </div>
          <div className="ft-problem__main">
            <p className="ft-problem__name">
              <Link className="ft-link" href={routes.charge(row.charge.grant_id, row.charge.id)}>
                {row.charge.description}
              </Link>
              {row.charge.vendor && <span className="ft-caption"> · {row.charge.vendor}</span>}
            </p>
            {failing(row.status.reasons).map((r) => (
              <ReasonLine key={`${r.check}:${r.problem}`} reason={r} />
            ))}
          </div>
          <div className="ft-problem__side">
            <span className="ft-amount">{money(row.charge.amount_cents)}</span>
            <ChargeStatusBadge status={row.status} />
          </div>
        </>
      );
    case "held_mail":
      return (
        <>
          <div className="ft-problem__what">
            <span className="ft-tag">Mail</span>
          </div>
          <div className="ft-problem__main">
            <p className="ft-problem__name">
              <Link className="ft-link" href={routes.mail(row.held.workspace_id)}>
                {row.held.subject || "No subject"}
              </Link>
            </p>
            <p className="ft-problem__text">
              {HOLD_REASON_LABELS[row.held.reason]}
              {row.held.sender && <> · {row.held.sender}</>}
            </p>
          </div>
          <div className="ft-problem__side ft-caption">Gmail · {date(row.held.held_at)}</div>
        </>
      );
  }
}

/**
 * The problem list, in the order the server sends it: grant problems, then
 * records, files and held mail, then charges by bucket, oldest first (answer
 * 1 of #22). Each row links to its page through routes.
 * The screen never sorts or filters it.
 */
export function ProblemList({ rows }: { rows: ProblemRow[] }) {
  if (rows.length === 0) {
    return <p className="ft-empty">Nothing on the problem list.</p>;
  }
  return (
    <ol className="ft-problems" aria-label="Problem list">
      {rows.map((row, i) => (
        <li className="ft-problem" key={rowKey(row, i)} data-kind={row.kind}>
          <Row row={row} />
        </li>
      ))}
    </ol>
  );
}
