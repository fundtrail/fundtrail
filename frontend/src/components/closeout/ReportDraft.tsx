"use client";

import { useEffect, useState } from "react";
import { ApiError, useApi, type Id, type SignOffState } from "@/lib/api";
import { date } from "@/lib/format";

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 501) {
      return "The evidence report isn't built yet: the server answered 501 (Not Implemented).";
    }
    if (typeof error.detail === "string") return error.detail;
    return `The report couldn't be loaded (status ${error.status}).`;
  }
  return "The report couldn't be loaded.";
}

/**
 * The evidence report (decision 0022). GET /grants/{id}/report gives the
 * current draft as a PDF; the screen fetches it with the accountant's token and
 * offers it to open or save. A signed report is the one stored at sign-off.
 */
export function ReportDraft({ grantId, signOff }: { grantId: Id; signOff: SignOffState }) {
  const api = useApi();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      const pdf = await api.getReport(grantId);
      setUrl(URL.createObjectURL(pdf));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const signed = signOff.sign_off ?? null;
  return (
    <section className="ft-panel" aria-labelledby="report-heading">
      <div className="ft-panel__head">
        <h2 id="report-heading" className="ft-heading">
          Evidence report
        </h2>
      </div>
      <p>
        {signed ? (
          <>
            Signed off {date(signed.written_at)}. The signed report is stored as it was signed. The draft below is
            today&apos;s, made fresh from the records.
          </>
        ) : (
          <>Draft. It&apos;s made fresh from the records each time you open it.</>
        )}
      </p>
      <p>
        <button type="button" className={`ft-btn${busy ? " is-busy" : ""}`} disabled={busy} onClick={() => void load()}>
          {busy ? "Making the draft…" : url ? "Make the draft again" : "Make the draft"}
        </button>{" "}
        {url && (
          <>
            <a className="ft-link" href={url} target="_blank" rel="noopener">
              Open the draft (PDF)
            </a>
            {" · "}
            <a className="ft-link" href={url} download={`evidence-report-draft-${grantId}.pdf`}>
              Save it
            </a>
          </>
        )}
      </p>
      {error && (
        <p className="ft-error" role="alert">
          {error}
        </p>
      )}
      <p className="ft-caption">
        Attach the signed report to the university&apos;s closeout step, next to its own ledger report. FundTrail files
        nothing with the university or the funder.
      </p>
    </section>
  );
}
