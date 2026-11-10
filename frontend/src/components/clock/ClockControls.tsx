"use client";

import { useId, useState, type FormEvent } from "react";
import { ApiError, useApi, useClock, useRefresh, type ArrivalSource, type Clock, type Id } from "@/lib/api";
import { date } from "@/lib/format";
import styles from "./ClockControls.module.css";

const ARRIVAL_SOURCE_LABELS: Record<ArrivalSource, string> = {
  ledger: "ledger line",
  gmail: "from Gmail",
  drive: "from Google Drive",
  upload: "upload",
};

/** "YYYY-MM-DD" of a UTC timestamp. */
function dayOf(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}

/** The day after `iso`'s UTC day, the earliest a chosen date can be. */
function dayAfter(iso: string): string {
  const d = new Date(`${dayOf(iso)}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === "string") return error.detail;
    if (error.problems) return error.problems.join(" ");
    return `The clock didn't move (status ${error.status}).`;
  }
  return "The clock didn't move.";
}

/**
 * The workspace clock in the sidebar (decision 0023). Every workspace shows its
 * "now". Only a simulated clock, the demo workspace's, has controls: go to the
 * next arrival, or go forward to a chosen date. There's no going back: the date
 * field starts the day after "now", and the server refuses anything earlier.
 */
export function ClockControls({ workspaceId }: { workspaceId: Id | null }) {
  const clock = useClock(workspaceId);
  if (!clock.data) {
    return (
      <div className="ft-sidebar__clock">
        <span className="ft-label">Clock</span>
        <span className="ft-caption">…</span>
      </div>
    );
  }
  return (
    <ClockPanel
      workspaceId={workspaceId!}
      clock={clock.data}
      onMoved={(moved) => clock.mutate(moved, { revalidate: false })}
    />
  );
}

/** The clock and, when simulated, its controls. Split out so tests can give it a clock. */
export function ClockPanel({
  workspaceId,
  clock,
  onMoved,
}: {
  workspaceId: Id;
  clock: Clock;
  onMoved: (clock: Clock) => unknown;
}) {
  const api = useApi();
  const refresh = useRefresh();
  const [chosen, setChosen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dateId = useId();

  const earliest = dayAfter(clock.now);
  const chosenIsForward = chosen !== "" && chosen >= earliest;
  const next = clock.next_arrival ?? null;
  const nextAt = next?.at ?? clock.next_arrival_at ?? null;

  async function move(to: string | null) {
    setBusy(true);
    setError(null);
    try {
      const moved = await api.moveClock(workspaceId, to ? { to } : {});
      await onMoved(moved);
      setChosen("");
      // Everything on screen may have changed with the time.
      await refresh();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  function goForward(event: FormEvent) {
    event.preventDefault();
    if (!chosenIsForward || busy) return;
    void move(`${chosen}T00:00:00Z`);
  }

  return (
    <div className="ft-sidebar__clock" aria-label="Workspace clock" role="group">
      <span className="ft-label">Clock</span>
      <span className="ft-num" data-testid="clock-now">
        {date(clock.now)}
        {clock.simulated && <span className="ft-caption"> · demo clock</span>}
      </span>
      {clock.simulated && (
        <div className={styles.controls}>
          <span className="ft-caption" data-testid="next-arrival">
            {nextAt ? (
              <>
                Next arrival: {date(nextAt)}
                {next && (
                  <>
                    , {next.name} ({ARRIVAL_SOURCE_LABELS[next.source]})
                  </>
                )}
              </>
            ) : (
              "Nothing is waiting for the clock."
            )}
          </span>
          <button
            type="button"
            className={`ft-btn ft-btn--sm${busy ? " is-busy" : ""}`}
            disabled={!nextAt || busy}
            onClick={() => void move(null)}
          >
            Go to next arrival
          </button>
          <form onSubmit={goForward} className={styles.forward}>
            <label htmlFor={dateId} className="ft-caption">
              Go forward to
            </label>
            <input
              id={dateId}
              type="date"
              min={earliest}
              value={chosen}
              onChange={(e) => setChosen(e.target.value)}
            />
            <button type="submit" className="ft-btn ft-btn--sm" disabled={!chosenIsForward || busy}>
              Go
            </button>
            {chosen !== "" && !chosenIsForward && (
              <span className="ft-caption" role="status">
                The clock only moves forward. Pick {date(earliest)} or later.
              </span>
            )}
          </form>
          {error && (
            <span className="ft-error" role="alert">
              {error}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
