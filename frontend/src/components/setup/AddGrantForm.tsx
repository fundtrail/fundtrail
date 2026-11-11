"use client";

import Link from "next/link";
import { useId, useState, type FormEvent } from "react";
import { ApiError, useApi, useRefresh, type Grant, type Id } from "@/lib/api";
import { routes } from "@/lib/routes";
import { DropWell } from "./DropWell";
import "./setup.css";

type AddState = { status: "idle" } | { status: "sending" } | { status: "added"; grant: Grant } | { status: "failed"; message: string };

/**
 * Adding a grant: the accountant drops in the award letter (product.md,
 * Grants). The grant comes back at once and its terms appear as the agent
 * writes them (contracts.md section 12), so this points to the terms page.
 *
 * `main` says whether this side carries the page's one main button, which
 * goes to the side the accountant used last; `onUse` says a file was chosen.
 * Alone, the form carries it once a file is chosen.
 */
export function AddGrantForm({ workspaceId, main = true, onUse }: { workspaceId: Id; main?: boolean; onUse?: () => void }) {
  const api = useApi();
  const refresh = useRefresh();
  const inputId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [state, setState] = useState<AddState>({ status: "idle" });

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setState({ status: "sending" });
    try {
      const grant = await api.createGrant(workspaceId, file, file.name);
      setState({ status: "added", grant });
      void refresh();
    } catch (error) {
      const message = error instanceof ApiError ? error.message : "Couldn't add the grant. Try again.";
      setState({ status: "failed", message });
    }
  }

  if (state.status === "added") {
    return (
      <div className="ft-panel ft-pad" role="status">
        <p className="ft-strong">Grant added.</p>
        <p>The agent is reading the award letter. Its terms appear as it writes them, and wait for you to confirm them.</p>
        <p className="ft-actions">
          <Link className={`ft-btn${main ? " ft-btn--main" : ""}`} href={routes.terms(state.grant.id)}>
            Confirm its terms
          </Link>
          <Link className="ft-link" href={routes.grant(state.grant.id)}>
            Open the grant
          </Link>
        </p>
      </div>
    );
  }

  const sending = state.status === "sending";

  return (
    <form className="ft-panel ft-choice-card" onSubmit={(e) => void submit(e)} aria-label="Your own grant">
      <h2 className="ft-heading">Your own grant</h2>
      <div className="ft-field">
        <label htmlFor={inputId} className="ft-label">
          Award letter
        </label>
        <DropWell file={file} what="the award letter">
          <input
            id={inputId}
            type="file"
            aria-describedby={`${inputId}-help`}
            onChange={(e) => {
              const chosen = e.target.files?.[0] ?? null;
              setFile(chosen);
              if (chosen) onUse?.();
            }}
          />
        </DropWell>
        <p id={`${inputId}-help`} className="ft-caption">
          The agent reads the terms from it: dates, budget lines, people, approval rules and anything else it says.
        </p>
      </div>
      {state.status === "failed" && (
        <p className="ft-error" role="alert">
          {state.message}
        </p>
      )}
      <div className="ft-choice-card__actions">
        <button type="submit" className={`ft-btn${file && main ? " ft-btn--main" : ""}${sending ? " is-busy" : ""}`} disabled={!file || sending}>
          Add the grant
        </button>
      </div>
    </form>
  );
}
