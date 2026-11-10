"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { grantName } from "@/components/GrantList";
import { ApiError, SampleRefusalError, type GrantSummary, type Id, type SampleChoice, type SampleCreate, type SampleOption, type SampleRefusal } from "@/lib/api";
import { routes } from "@/lib/routes";
import "./setup.css";

// Wording here is a placeholder until the docs give it.

/** The grant a refusal names: the blocking larger-live sample. */
interface BlockingGrant {
  id: Id;
  name: string;
}

/**
 * A 409's SampleRefusal (ruling 41), read from FastAPI's `detail`: the
 * server's message, and the blocking larger-live sample when it names one.
 * Null when the body isn't a refusal.
 */
export function readRefusal(detail: unknown): { message: string; blocking: BlockingGrant | null } | null {
  if (typeof detail !== "object" || detail === null) return null;
  const refusal = detail as Partial<SampleRefusal>;
  if (typeof refusal.message !== "string") return null;
  const grant = refusal.grant?.grant;
  const blocking = grant && typeof grant.id === "string" ? { id: grant.id, name: grantName(refusal.grant!) } : null;
  return { message: refusal.message, blocking };
}

type OpenState =
  | { status: "idle" }
  | { status: "confirming" }
  | { status: "opening" }
  | { status: "refused"; message: string; blocking: BlockingGrant | null };

/**
 * The Sample card: a dropdown of the samples GET /samples offers, nothing
 * chosen at first, with the chosen one's description, and Open. An option that
 * needs a confirm step asks for it first; an unavailable one shows its reason.
 * A sample opens as one grant in the user's own workspace.
 */
export function SampleCard({
  options,
  openSample,
  onOpened,
}: {
  options: SampleOption[];
  openSample: (body: SampleCreate) => Promise<GrantSummary>;
  onOpened: (grantId: Id) => void;
}) {
  const selectId = useId();
  const [choice, setChoice] = useState<SampleChoice | "">("");
  const [state, setState] = useState<OpenState>({ status: "idle" });
  const [nudge, setNudge] = useState(false);
  const option = options.find((o) => o.choice === choice) ?? null;

  async function open(confirmed: boolean) {
    if (!option) return;
    setState({ status: "opening" });
    try {
      const summary = await openSample({ choice: option.choice, confirmed });
      setState({ status: "idle" });
      onOpened(summary.grant.id);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        const refusal = readRefusal(error instanceof SampleRefusalError ? error.refusal : error.detail);
        setState({ status: "refused", message: refusal?.message ?? error.message, blocking: refusal?.blocking ?? null });
      } else {
        setState({ status: "refused", message: error instanceof ApiError ? error.message : "Couldn't open the sample. Try again.", blocking: null });
      }
    }
  }

  function clickOpen() {
    if (!option) {
      setNudge(true);
      return;
    }
    if (option.needs_confirm) setState({ status: "confirming" });
    else void open(false);
  }

  const busy = state.status === "opening";

  return (
    <section className="ft-panel ft-pad" aria-labelledby={`${selectId}-heading`}>
      <h2 id={`${selectId}-heading`} className="ft-heading">
        Sample
      </h2>
      <div className="ft-field">
        <label htmlFor={selectId} className="ft-label">
          Which sample
        </label>
        <select
          id={selectId}
          value={choice}
          onChange={(e) => {
            setChoice(e.target.value as SampleChoice | "");
            setNudge(false);
            setState({ status: "idle" });
          }}
        >
          <option value="">Choose a sample</option>
          {options.map((o) => (
            <option key={o.choice} value={o.choice}>
              {o.available ? o.name : `${o.name} (unavailable)`}
            </option>
          ))}
        </select>
      </div>

      <p aria-live="polite">{option ? option.description : "A sample grant to try FundTrail on, added to this workspace."}</p>
      {option && !option.available && (
        <p className="ft-error">{option.unavailable_reason ?? "This sample isn't available right now."}</p>
      )}

      {state.status === "confirming" && option ? (
        <div className="ft-typeterm" role="group" aria-label="Confirm the sample">
          <p>{option.name} is read live by the agent from the start. Start it?</p>
          <div className="ft-actions">
            <button type="button" className="ft-btn ft-btn--main ft-btn--sm" onClick={() => void open(true)}>
              Start it
            </button>
            <button type="button" className="ft-btn ft-btn--sm" onClick={() => setState({ status: "idle" })}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="ft-actions">
          <button type="button" className="ft-btn ft-btn--main" disabled={busy || (option !== null && !option.available)} onClick={clickOpen}>
            Open
          </button>
        </div>
      )}

      {nudge && (
        <p className="ft-error" role="alert">
          Choose a sample first.
        </p>
      )}
      {state.status === "refused" && (
        <p className="ft-error" role="alert">
          {state.message}
          {state.blocking && (
            <>
              {" "}
              <Link className="ft-link" href={routes.grant(state.blocking.id)}>
                {state.blocking.name}
              </Link>
            </>
          )}
        </p>
      )}
    </section>
  );
}
