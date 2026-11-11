"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError, useApi, type FtRecord, type Id, type SignOffState, type SnapshotChange } from "@/lib/api";
import { date } from "@/lib/format";
import "./closeout.css";

const CHANGE_KIND_LABELS: Record<SnapshotChange["kind"], string> = {
  charge: "Charge",
  problem_list: "Problem list",
  total: "Total",
};

function StateLine({ signOff }: { signOff: SignOffState }) {
  const record = signOff.sign_off ?? null;
  if (signOff.state === "not_signed" || !record) {
    return (
      <p className="ft-co-state" data-testid="sign-off-state">
        Not signed off yet.
      </p>
    );
  }
  return (
    <div className="ft-co-state" data-testid="sign-off-state">
      <p className="ft-co-state__head">
        <span className="ft-strong">{signOff.state === "changed" ? "Changed since sign-off." : "Signed off."}</span>{" "}
        Signed {date(record.written_at)}.
      </p>
      {record.data.note && (
        <div className="ft-co-quote">
          <span className="ft-label">Note</span>
          <blockquote className="ft-co-note">{record.data.note}</blockquote>
        </div>
      )}
      <p className="ft-caption">
        Signed report checksum (SHA-256): <span className="ft-id">{record.data.report_sha256}</span>
      </p>
      {signOff.state === "changed" && (signOff.changes ?? []).length > 0 && (
        <table className="ft-ledger ft-co-changes" aria-label="What changed since sign-off">
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
 * Withdrawing the current sign-off: a retraction that replaces it (decision
 * 0022, contracts.md section 1). Nothing is deleted; the signed report stays on
 * file. The reason is optional, as the contract has it.
 */
function WithdrawSignOff({
  grantId,
  signOffId,
  onWithdrawn,
}: {
  grantId: Id;
  signOffId: Id;
  onWithdrawn: (record: FtRecord) => unknown;
}) {
  const api = useApi();
  const reasonId = useId();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [withdrawn, setWithdrawn] = useState<FtRecord | null>(null);

  async function withdraw(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    const text = reason.trim();
    try {
      const record = await api.writeRecord(grantId, {
        data: { kind: "retraction", reason: text === "" ? null : text },
        replaces_id: signOffId,
      });
      setWithdrawn(record);
      setReason("");
      await onWithdrawn(record);
    } catch (e) {
      if (e instanceof ApiError) {
        setError(
          (e.problems ?? [typeof e.detail === "string" ? e.detail : `The sign-off wasn't withdrawn (status ${e.status}).`]).join(" "),
        );
      } else {
        setError("The sign-off wasn't withdrawn.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (withdrawn) {
    return (
      <p className="ft-co-done" role="status">
        Sign-off withdrawn {date(withdrawn.written_at)}. The signed report stays on file.
      </p>
    );
  }
  return (
    <form className="ft-co-withdraw ft-field" onSubmit={withdraw} aria-label="Withdraw the sign-off">
      <p>
        <label htmlFor={reasonId} className="ft-field__label">
          Reason for withdrawing
        </label>{" "}
        <span className="ft-caption">(optional)</span>
      </p>
      <div className="ft-co-withdraw__row">
        <input
          id={reasonId}
          className="ft-input"
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <button type="submit" className={`ft-btn ft-btn--sm${busy ? " is-busy" : ""}`} disabled={busy}>
          Withdraw the sign-off
        </button>
      </div>
      {error && (
        <p className="ft-error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

/** How long a reason is withdrawn from screen readers on a press, so it's announced again. */
const REANNOUNCE_MS = 150;

/**
 * Rulings 72 and 79: why signing off can't be done now, in the server's words,
 * under the control it blocks and named as that control's description. A polite
 * live region: a new or changed reason is announced, and a refetch that brings
 * the same reason changes no text, so it announces nothing. A press on the
 * unavailable control hides the text from screen readers for a moment and
 * brings it back, which announces it again; on screen it never moves or blinks.
 */
function UnavailableReason({ id, reason, blank }: { id: string; reason: string; blank: boolean }) {
  return (
    <p className="ft-co-unavailable" id={id} role="status">
      {blank ? <span aria-hidden="true">{reason}</span> : reason}
    </p>
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
  // Once signed, signing again is a quiet action: the form opens in place when asked.
  const [formOpen, setFormOpen] = useState(false);
  const againRef = useRef<HTMLButtonElement>(null);
  // Set by Cancel, so closing the form hands focus back to "Sign off again".
  const returnFocus = useRef(false);
  // Rulings 72 and 79: the server says, in its own words, when signing off can't be done now.
  const unavailable = signOff.unavailable_reason?.trim() || null;
  // Pressing an unavailable control blanks its reason for a moment, so it's announced again.
  const [reasonBlank, setReasonBlank] = useState(false);
  const reannounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (reannounce.current) clearTimeout(reannounce.current);
    },
    [],
  );

  function announceUnavailable() {
    if (reannounce.current) clearTimeout(reannounce.current);
    setReasonBlank(true);
    reannounce.current = setTimeout(() => {
      reannounce.current = null;
      setReasonBlank(false);
    }, REANNOUNCE_MS);
  }

  // Opening the form to sign again puts the cursor in the note, the first thing to
  // fill in; closing it with Cancel puts focus back on "Sign off again".
  useEffect(() => {
    if (formOpen) {
      noteRef.current?.focus();
    } else if (returnFocus.current) {
      returnFocus.current = false;
      againRef.current?.focus();
    }
  }, [formOpen]);

  function cancel() {
    returnFocus.current = true;
    setFormOpen(false);
  }

  async function signOffNow(event: FormEvent) {
    event.preventDefault();
    if (unavailable) {
      announceUnavailable();
      return;
    }
    if (busy) return;
    setBusy(true);
    setRefusal(null);
    setSigned(null);
    const text = note.trim();
    try {
      const record = await api.writeRecord(grantId, { data: { kind: "sign_off", note: text === "" ? null : text } });
      setSigned(record);
      setNote("");
      setFormOpen(false);
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
  // Signed: the stored sign-off leads, and the form waits behind a quiet button.
  const showForm = !again || formOpen;
  const reasonId = `${noteId}-unavailable`;

  return (
    <section className="ft-co-sign" aria-labelledby="sign-off-heading">
      <div className="ft-co-sign__head">
        <h2 id="sign-off-heading" className="ft-heading">
          Sign-off
        </h2>
      </div>
      <StateLine signOff={signOff} />
      {signed && (
        <p className="ft-co-done" role="status">
          Signed off {date(signed.written_at)}. The report now carries your sign-off.
        </p>
      )}

      {showForm ? (
        <form className={`ft-co-form${again ? " is-again" : ""}`} onSubmit={signOffNow} aria-label="Sign off">
          <div className={`ft-field${refusal ? " is-invalid" : ""}`}>
            <label htmlFor={noteId} className="ft-field__label">
              Note
            </label>
            <textarea
              id={noteId}
              ref={noteRef}
              className="ft-textarea"
              rows={3}
              value={note}
              aria-describedby={`${noteId}-hint`}
              aria-invalid={refusal ? true : undefined}
              onChange={(e) => setNote(e.target.value)}
            />
            <span className="ft-field__hint" id={`${noteId}-hint`}>
              Required when any charge isn&apos;t ready for closeout or anything is still open. It goes into the report.
            </span>
          </div>
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
          <div className="ft-co-submit">
            <div className="ft-co-submit__row">
              {/* aria-disabled, not disabled, so the button and its reason stay reachable by keyboard. */}
              <button
                type="submit"
                className={`ft-btn ft-btn--approve ft-btn--main${busy ? " is-busy" : ""}`}
                disabled={busy}
                aria-disabled={unavailable ? true : undefined}
                aria-describedby={unavailable ? reasonId : undefined}
              >
                {again ? "Sign off again" : "Sign off"}
              </button>
              {again && (
                <button type="button" className="ft-btn ft-btn--sm ft-btn--quiet" onClick={cancel}>
                  Cancel
                </button>
              )}
            </div>
            {unavailable && <UnavailableReason id={reasonId} reason={unavailable} blank={reasonBlank} />}
          </div>
        </form>
      ) : (
        <div className="ft-co-again">
          <button
            ref={againRef}
            type="button"
            className="ft-btn ft-btn--sm"
            aria-disabled={unavailable ? true : undefined}
            aria-describedby={unavailable ? reasonId : undefined}
            onClick={() => (unavailable ? announceUnavailable() : setFormOpen(true))}
          >
            Sign off again
          </button>
          {unavailable && <UnavailableReason id={reasonId} reason={unavailable} blank={reasonBlank} />}
        </div>
      )}

      {signOff.sign_off && !signed && (
        <WithdrawSignOff grantId={grantId} signOffId={signOff.sign_off.id} onWithdrawn={onSigned} />
      )}
      <p className="ft-co-foot">
        Your supervisor approves the closeout in the university&apos;s own system. The report prints a blank
        &quot;Reviewed by&quot; line for them.
      </p>
    </section>
  );
}
