"use client";

import { useEffect, useState } from "react";
import { ApiError, useApi, type Id, type SignOffState } from "@/lib/api";
import { date } from "@/lib/format";
import "./closeout.css";

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
 * offers it to open or save. A signed report is the one stored at sign-off,
 * fetched through its sign-off record (GET /records/{record_id}/report) and
 * offered the same way, above the draft, whenever the server sends a sign-off.
 */
export function ReportDraft({ grantId, signOff }: { grantId: Id; signOff: SignOffState }) {
  const api = useApi();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  // The signed report, kept with the sign-off it came from: signing again makes a new one.
  const [signedBusy, setSignedBusy] = useState(false);
  const [signedError, setSignedError] = useState<string | null>(null);
  const [signedFile, setSignedFile] = useState<{ recordId: Id; url: string } | null>(null);

  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);

  useEffect(() => {
    return () => {
      if (signedFile) URL.revokeObjectURL(signedFile.url);
    };
  }, [signedFile]);

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
  // A file fetched for an earlier sign-off isn't offered for a newer one.
  const signedUrl = signed && signedFile?.recordId === signed.id ? signedFile.url : null;

  async function loadSigned(recordId: Id) {
    setSignedBusy(true);
    setSignedError(null);
    try {
      const pdf = await api.getSignedReport(recordId);
      setSignedFile({ recordId, url: URL.createObjectURL(pdf) });
    } catch (e) {
      setSignedError(errorText(e));
    } finally {
      setSignedBusy(false);
    }
  }

  return (
    <section className="ft-co-report" aria-labelledby="report-heading">
      <div className="ft-co-report__head">
        <h2 id="report-heading" className="ft-heading">
          Evidence report
        </h2>
      </div>
      <p>
        {signed ? (
          <>
            {/* Once signed, the signed report is the page's main thing: its line leads. */}
            <span className="ft-co-report__lead">Signed off {date(signed.written_at)}.</span> The signed report is
            stored as it was signed. The draft below is today&apos;s, made fresh from the records.
          </>
        ) : (
          <>Draft. It&apos;s made fresh from the records each time you open it.</>
        )}
      </p>
      {signed && (
        <>
          {/* The signed report leads once signed; the draft's controls follow, as before. */}
          <div className="ft-co-actions" role="group" aria-label="Signed report">
            {signedUrl ? (
              <>
                <a className="ft-link" href={signedUrl} target="_blank" rel="noopener">
                  Open the signed report (PDF)
                </a>
                <a className="ft-link" href={signedUrl} download={`evidence-report-signed-${grantId}.pdf`}>
                  Save it
                </a>
              </>
            ) : (
              <button
                type="button"
                className={`ft-btn${signedBusy ? " is-busy" : ""}`}
                disabled={signedBusy}
                onClick={() => void loadSigned(signed.id)}
              >
                {signedBusy ? "Getting the signed report…" : "Get the signed report"}
              </button>
            )}
          </div>
          {signedError && (
            <p className="ft-error" role="alert">
              {signedError}
            </p>
          )}
        </>
      )}
      <div className="ft-co-actions">
        <button type="button" className={`ft-btn ft-btn--sm${busy ? " is-busy" : ""}`} disabled={busy} onClick={() => void load()}>
          {busy ? "Making the draft…" : url ? "Make the draft again" : "Make the draft"}
        </button>
        {url && (
          <>
            <a className="ft-link" href={url} target="_blank" rel="noopener">
              Open the draft (PDF)
            </a>
            <a className="ft-link" href={url} download={`evidence-report-draft-${grantId}.pdf`}>
              Save it
            </a>
          </>
        )}
      </div>
      {error && (
        <p className="ft-error" role="alert">
          {error}
        </p>
      )}
      <p className="ft-co-foot">
        Attach the signed report to the university&apos;s closeout step, next to its own ledger report. FundTrail files
        nothing with the university or the funder.
      </p>
    </section>
  );
}
