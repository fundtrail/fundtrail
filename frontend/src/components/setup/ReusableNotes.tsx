import Link from "next/link";
import type { ReusableNoteView } from "@/lib/api";
import { date, money } from "@/lib/format";
import { routes } from "@/lib/routes";
import "./setup.css";

/**
 * The grant's reusable notes (product.md, What the user sees): for each, what
 * it excuses, who wrote it and when, and every charge it covered. Code does the
 * matching; this only shows what the server sends.
 */
export function ReusableNotes({ notes }: { notes: ReusableNoteView[] }) {
  if (notes.length === 0) {
    return <p className="ft-empty">No reusable notes. A note the accountant chooses to reuse when accepting a problem shows here.</p>;
  }
  return (
    <ul className="ft-notes-list" aria-label="Reusable notes">
      {notes.map(({ note, charge, amount_limit_cents, covered = [] }) => (
        <li key={note.id} className="ft-term">
          <p className="ft-strong">“{note.data.note}”</p>
          <p className="ft-caption">
            Written by {note.author === "user" ? "the accountant" : "the agent"}, {date(note.written_at)}, on{" "}
            <Link className="ft-link" href={routes.charge(charge.grant_id, charge.id)}>
              {charge.ledger_line_id}
            </Link>
          </p>
          <dl className="ft-term__values">
            <div className="ft-term__value">
              <dt className="ft-label">Excuses</dt>
              <dd>
                <span className="ft-id">
                  {note.data.reason.check} · {note.data.reason.problem}
                </span>
              </dd>
            </div>
            <div className="ft-term__value">
              <dt className="ft-label">Ledger account</dt>
              <dd>{charge.account}</dd>
            </div>
            <div className="ft-term__value">
              <dt className="ft-label">Vendor</dt>
              <dd>{charge.vendor ?? "None on the ledger line"}</dd>
            </div>
            <div className="ft-term__value">
              <dt className="ft-label">Up to</dt>
              <dd className="ft-amount">{money(amount_limit_cents)}</dd>
            </div>
          </dl>
          <p className="ft-label">Charges it covered</p>
          {covered.length === 0 ? (
            <p className="ft-caption">None yet.</p>
          ) : (
            <ul aria-label="Charges it covered">
              {covered.map((c) => (
                <li key={c.id}>
                  <Link className="ft-link" href={routes.charge(c.grant_id, c.id)}>
                    {c.ledger_line_id}
                  </Link>{" "}
                  <span className="ft-caption">
                    {date(c.transaction_date)} · {c.description}
                  </span>{" "}
                  <span className="ft-amount">{money(c.amount_cents)}</span>
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}
