"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { ApiError, useApi, type FtRecord, type Id, type SignOffState, type SnapshotChange } from "@/lib/api";
import { date } from "@/lib/format";

const CHANGE_KIND_LABELS: Record<SnapshotChange["kind"], string> = {
  charge: "Charge",
  problem_list: "Problem list",
  total: "Total",
};

function StateLine({ signOff }: { signOff: SignOffState }) {
  const record = signOff.sign_off ?? null;
  if (signOff.state === "not_signed" || !record) {
    return <p data-testid="sign-off-state">Not signed off yet.</p>;
  }
  return (
    <div data-testid="sign-off-state">
      <p>
        <span className="ft-strong">{signOff.state === "changed" ? "Changed since sign-off." : "Signed off."}</span>{" "}
        Signed {date(record.written_at)}.
      </p>
      {record.data.note && (
        <p>
          <span className="ft-label">Note</span>
          <br />
          {record.data.note}
        </p>
      )}
      <p className="ft-caption">
        Signed report checksum (SHA-256): <span className="ft-id">{record.data.report_sha256}</span>
      </p>
      {signOff.state === "changed" && (signOff.changes ?? []).length > 0 && (
        <table className="ft-ledger" aria-label="What changed since sign-off">
          <thead>
            <tr>
              <th scope="col">What</th>
              <th scope="col">Which</th>
              <th scope="col">At sign-off</th>
              <th scope="col">Now</th>
            </tr>
          </thead>
          <tbody>
            {(signOff.changes ?? []).map((c) => (
              <tr key={`${c.kind}:${c.subject}`}>
                <td>{CHANGE_KIND_LABELS[c.kind]}</td>
                <td className="ft-id">{c.subject}</td>
                <td>{c.before ?? <span className="ft-caption">Not there</span>}</td>
                <td>{c.after ?? <span className="ft-caption">Gone</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/**
 * The accountant's sign-off on the evidence report (decision 0022). It sends
 * only the note; the server decides whether the sign-off stands. A note is
 * required whenever anything is still open, and a sign-off is refused while an
 * agent run for the grant is running or queued: the screen shows the server's
 * answer as it comes and checks neither rule itself.
 */
export function SignOffPanel({
  grantId,
  signOff,
  onSigned,
}: {
  grantId: Id;
  signOff: SignOffState;
  onSigned: (record: FtRecord) => unknown;
}) {
  const api = useApi();
  const noteId = useId();
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const [signed, setSigned] = useState<FtRecord | null>(null);

  async function signOffNow(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setRefusal(null);
    setSigned(null);
    const text = note.trim();
    try {
      const record = await api.writeRecord(grantId, { data: { kind: "sign_off", note: text === "" ? null : text } });
      setSigned(record);
      setNote("");
      await onSigned(record);
    } catch (e) {
      if (e instanceof ApiError) {
        setRefusal(e.problems ?? [typeof e.detail === "string" ? e.detail : `The sign-off didn't go through (status ${e.status}).`]);
      } else {
        setRefusal(["The sign-off didn't go through."]);
      }
      noteRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  const again = signOff.state !== "not_signed";
  return (
    <section className="ft-panel" aria-labelledby="sign-off-heading">
      <div className="ft-panel__head">
        <h2 id="sign-off-heading" className="ft-heading">
          Sign-off
        </h2>
      </div>
      <StateLine signOff={signOff} />

      <form onSubmit={signOffNow} aria-label="Sign off">
        <p>
          <label htmlFor={noteId} className="ft-strong">
            Note
          </label>
          <br />
          <span className="ft-caption" id={`${noteId}-hint`}>
            Required when any charge isn&apos;t ready for closeout or anything is still open. It goes into the report.
          </span>
        </p>
        <textarea
          id={noteId}
          ref={noteRef}
          rows={4}
          cols={60}
          value={note}
          aria-describedby={`${noteId}-hint`}
          aria-invalid={refusal ? true : undefined}
          onChange={(e) => setNote(e.target.value)}
        />
        {refusal && (
          <div className="ft-error" role="alert">
            {refusal.length === 1 ? (
              refusal[0]
            ) : (
              <ul>
                {refusal.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <p>
          <button type="submit" className={`ft-btn ft-btn--main${busy ? " is-busy" : ""}`} disabled={busy}>
            {again ? "Sign off again" : "Sign off"}
          </button>
        </p>
      </form>

      {signed && (
        <p role="status">Signed off {date(signed.written_at)}. The report now carries your sign-off.</p>
      )}
      <p className="ft-caption">
        Your supervisor approves the closeout in the university&apos;s own system. The report prints a blank
        &quot;Reviewed by&quot; line for them.
      </p>
    </section>
  );
}
