"use client";

import { useId, useState, type FormEvent } from "react";
import { DropWell } from "@/components/setup/DropWell";
import { ApiError, useApi, useRefresh, type Id, type LedgerUploadResult } from "@/lib/api";

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (error.problems) return error.problems.join(" ");
    return `The upload failed (status ${error.status}).`;
  }
  return "The upload failed.";
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * Putting a grant's ledger file in (contracts.md section 13): CSV or Excel, one
 * file per grant. The result says how many lines were added and how many were
 * already on file, and lists every rejected row with its number and the
 * server's reason, as it comes.
 */
export function LedgerUpload({ grantId }: { grantId: Id }) {
  const api = useApi();
  const refresh = useRefresh();
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ fileName: string; body: LedgerUploadResult } | null>(null);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = await api.uploadLedger(grantId, file, file.name);
      setResult({ fileName: file.name, body });
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  const { added, already_present: present, rejected } = result?.body ?? { added: 0, already_present: 0, rejected: [] };

  return (
    <div className="ft-panel ft-upload">
      <form className="ft-upload__form" onSubmit={upload} aria-label="Upload the ledger file">
        <div className="ft-field">
          <label htmlFor={inputId} className="ft-label">
            Ledger file
          </label>
          <DropWell file={file} what="the ledger file">
            <input
              id={inputId}
              type="file"
              aria-describedby={`${inputId}-columns`}
              accept=".csv,.xlsx,.xls,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </DropWell>
        </div>
        <div id={`${inputId}-columns`} className="ft-upload__columns">
          <p>CSV or Excel, one file for this grant. The first row names the columns:</p>
          <ul className="ft-upload__cols">
            {["line_id", "transaction_date", "posting_date", "amount", "description", "account"].map((c) => (
              <li key={c}>
                <code>{c}</code>
              </li>
            ))}
          </ul>
          <p>
            with <code>vendor</code>, <code>reference</code> and <code>original_line_id</code> if you have them.
          </p>
        </div>
        <div className="ft-upload__actions">
          <button type="submit" className={`ft-btn ft-btn--main${busy ? " is-busy" : ""}`} disabled={!file || busy}>
            {busy ? "Uploading…" : "Upload"}
          </button>
        </div>
      </form>

      {error && (
        <p className="ft-error ft-upload__error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <section className="ft-upload__result" aria-label="Upload result" role="status">
          <p className="ft-heading">{result.fileName}</p>
          <ul className="ft-found">
            <li className={added > 0 ? "is-done" : undefined}>{plural(added, "line added", "lines added")}</li>
            <li>{plural(present, "line already on file, skipped", "lines already on file, skipped")}</li>
            <li>{plural(rejected.length, "row rejected", "rows rejected")}</li>
          </ul>
          {rejected.length > 0 && (
            <>
              <div className="ft-upload__rows">
                <table className="ft-ledger">
                  <thead>
                    <tr>
                      <th scope="col">Row</th>
                      <th scope="col">Why it was rejected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rejected.map((r) => (
                      <tr key={`${r.row}-${r.message}`}>
                        <td className="ft-num">
                          <span className="ft-id">{r.row}</span>
                        </td>
                        <td>{r.message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="ft-caption">
                Row 1 is the first row after the header. Fix the rows and upload the file again. Lines already on file
                are skipped.
              </p>
            </>
          )}
        </section>
      )}
    </div>
  );
}
