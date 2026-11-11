import Link from "next/link";
import type { GrantSummary } from "@/lib/api";
import { date } from "@/lib/format";
import { grantDisplayName, useGrantDisplayName } from "@/lib/grantName";
import { routes } from "@/lib/routes";

/**
 * A grant's name, without the sample choices: "Untitled grant" until the award
 * letter is read. Screens that can should use useGrantDisplayName (lib/grantName),
 * which names a sample grant by its sample.
 */
export function grantName(summary: GrantSummary): string {
  return grantDisplayName(summary);
}

/**
 * The workspace's grants, one row each (answer 7 of #22): award number, title,
 * end date in force, charges ready out of total, rows on its problem list, and
 * the next closeout date. Rows keep the server's order.
 */
export function GrantList({ grants }: { grants: GrantSummary[] }) {
  const nameOf = useGrantDisplayName();
  if (grants.length === 0) {
    return <p className="ft-empty">No grants in this workspace yet.</p>;
  }
  return (
    <div className="ft-panel">
      <table className="ft-ledger">
        <thead>
          <tr>
            <th scope="col">Grant</th>
            <th scope="col">Ends</th>
            <th scope="col">Ready for closeout</th>
            <th scope="col">Problem list</th>
            <th scope="col">Next closeout date</th>
          </tr>
        </thead>
        <tbody>
          {grants.map((g) => (
            <tr key={g.grant.id}>
              <td>
                <Link className="ft-link ft-strong" href={routes.grant(g.grant.id)}>
                  {nameOf(g)}
                </Link>
                {g.grant.award_number && <div className="ft-id">{g.grant.award_number}</div>}
              </td>
              <td className="ft-num">{g.end_date ? date(g.end_date) : <span className="ft-caption">Not confirmed yet</span>}</td>
              <td>
                <span className="ft-num">
                  {g.charges_ready} of {g.charges_total}
                </span>{" "}
                <span className="ft-caption">charges</span>
              </td>
              <td>
                {g.on_problem_list > 0 ? (
                  <span className="ft-count ft-count--alert">
                    {g.on_problem_list}
                    <span className="ft-sr"> on the problem list</span>
                  </span>
                ) : (
                  <span className="ft-caption">None</span>
                )}
              </td>
              <td>
                {g.next_closeout ? (
                  <>
                    <div className="ft-num">{date(g.next_closeout.date)}</div>
                    <div className="ft-caption">{g.next_closeout.label}</div>
                  </>
                ) : (
                  <span className="ft-caption">None</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
