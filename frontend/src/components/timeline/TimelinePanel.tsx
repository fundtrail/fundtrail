"use client";

// The timeline panel on a sample grant's page, and only there (ruling 40,
// issue 165). It plays the sample's timeline; it never edits it. Every date
// comes from the server: the timeline's own now, never the browser's clock.
// Wording is a placeholder until the docs give it. First version, may change.

import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  SampleRefusalError,
  useApi,
  useRefresh,
  useTimeline,
  type ArrivalSource,
  type GrantSummary,
  type Id,
  type PlayedEvent,
  type TimelineEvent,
  type TimelineEventKind,
  type TimelineView,
  type UserDelivery,
} from "@/lib/api";
import { date, recordKindLabel } from "@/lib/format";
import { routes } from "@/lib/routes";
import "./timeline.css";

const SOURCE_WORDS: Record<ArrivalSource, string> = {
  ledger: "Ledger",
  gmail: "Gmail",
  drive: "Google Drive",
  upload: "Upload",
};

const KIND_WORDS: Record<TimelineEventKind, string> = {
  arrival: "Arrives",
  user_delivery: "For you to deliver",
  checks_date: "Date the checks work out",
};

function EventLine({ event }: { event: TimelineEvent }) {
  return (
    <>
      <span className="ft-num">{date(event.at)}</span>
      <span className="ft-strong">{event.name}</span>
      <span className="ft-caption">
        {KIND_WORDS[event.kind]}
        {event.source && <> · {SOURCE_WORDS[event.source]}</>}
      </span>
      {event.note && <span className="ft-caption">{event.note}</span>}
    </>
  );
}

/** What the agent wrote from one played event, as kinds and counts. */
function agentSummary(played: PlayedEvent): string {
  const records = played.agent_records ?? [];
  if (records.length === 0) return "The agent wrote nothing from it yet.";
  const counts = new Map<string, number>();
  for (const r of records) counts.set(recordKindLabel(r.data.kind), (counts.get(recordKindLabel(r.data.kind)) ?? 0) + 1);
  const parts = [...counts].map(([label, n]) => (n > 1 ? `${label} (${n})` : label));
  return `The agent wrote: ${parts.join(", ")}.`;
}

function JustHappened({ grantId, played }: { grantId: Id; played: PlayedEvent[] }) {
  return (
    <section className="ft-tl__part" aria-labelledby="tl-just">
      <h3 id="tl-just" className="ft-label">
        Just happened
      </h3>
      {played.length === 0 ? (
        <p className="ft-caption">Nothing yet.</p>
      ) : (
        <ul className="ft-tl__list">
          {played.map((p) => (
            <li key={p.event.id} className="ft-tl__item">
              <EventLine event={p.event} />
              <span>{agentSummary(p)}</span>
              {(p.charge_ids ?? []).map((chargeId) => (
                <Link key={chargeId} className="ft-link" href={routes.charge(grantId, chargeId)}>
                  Open the charge
                </Link>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Saves a file from a link: a signed link, or a data: link in fake mode. */
function saveFrom(url: string, name: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function Delivery({
  grantId,
  delivery,
  busy,
  act,
}: {
  grantId: Id;
  delivery: UserDelivery;
  busy: boolean;
  act: (run: () => Promise<unknown>) => Promise<void>;
}) {
  const api = useApi();
  const { event } = delivery;
  return (
    <li className="ft-tl__item">
      <EventLine event={event} />
      <span className="ft-tl__actions">
        <button
          type="button"
          className="ft-btn ft-btn--sm"
          disabled={busy}
          onClick={() => void act(async () => saveFrom((await api.deliveryFileUrl(grantId, event.id)).url, event.name))}
        >
          Get the file
        </button>
        <button type="button" className="ft-btn ft-btn--sm" disabled={busy} onClick={() => void act(() => api.deliverForMe(grantId, event.id))}>
          Deliver for me
        </button>
      </span>
    </li>
  );
}

function Now({
  grantId,
  view,
  busy,
  act,
}: {
  grantId: Id;
  view: TimelineView;
  busy: boolean;
  act: (run: () => Promise<unknown>) => Promise<void>;
}) {
  const { now } = view;
  const deliveries = now.deliveries ?? [];
  return (
    <section className="ft-tl__part" aria-labelledby="tl-now">
      <h3 id="tl-now" className="ft-label">
        Now
      </h3>
      <p>
        <span className="ft-num ft-strong">{date(now.now)}</span>
        {now.stopped_on && <> · stopped on {now.stopped_on.name}</>}
      </p>
      {view.catching_up && <p className="ft-caption">The agent is still catching up on what arrived.</p>}
      {deliveries.length > 0 && (
        <ul className="ft-tl__list" aria-label="For you to deliver">
          {deliveries.map((d) => (
            <Delivery key={d.event.id} grantId={grantId} delivery={d} busy={busy} act={act} />
          ))}
        </ul>
      )}
      <p>
        {now.waiting_on_problem_list > 0 ? (
          <Link className="ft-link" href={routes.problemList(grantId)}>
            {now.waiting_on_problem_list} waiting on the problem list
          </Link>
        ) : (
          <span className="ft-caption">Nothing waiting on the problem list.</span>
        )}
      </p>
    </section>
  );
}

function ComingUp({ events, finished }: { events: TimelineEvent[]; finished: boolean }) {
  return (
    <section className="ft-tl__part" aria-labelledby="tl-coming">
      <h3 id="tl-coming" className="ft-label">
        Coming up
      </h3>
      {events.length === 0 ? (
        <p className="ft-caption">{finished ? "The timeline has played to its end." : "Nothing else is coming up."}</p>
      ) : (
        <ol className="ft-tl__list">
          {events.map((e) => (
            <li key={e.id} className="ft-tl__item">
              <EventLine event={e} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** The day after a timestamp, as a date input takes it: "Go to a date" only moves forward. */
function dayAfter(iso: string): string {
  const d = new Date(iso);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function GoToDate({ now, busy, onGo }: { now: string; busy: boolean; onGo: (to: string) => void }) {
  const id = useId();
  const [value, setValue] = useState("");
  const min = dayAfter(now);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (value && value >= min) onGo(`${value}T00:00:00Z`);
  }
  return (
    <form className="ft-tl__goto" onSubmit={submit}>
      <label htmlFor={id} className="ft-label">
        Go to a date
      </label>
      <input id={id} type="date" min={min} value={value} onChange={(e) => setValue(e.target.value)} required />
      <button type="submit" className="ft-btn ft-btn--sm" disabled={busy || !value || value < min}>
        Go
      </button>
    </form>
  );
}

function StartOver({ busy, onStartOver }: { busy: boolean; onStartOver: () => Promise<boolean> }) {
  const [asking, setAsking] = useState(false);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (asking) cancel.current?.focus();
  }, [asking]);
  return (
    <div className="ft-tl__startover">
      {!asking ? (
        <button type="button" className="ft-btn ft-btn--sm" disabled={busy} onClick={() => setAsking(true)}>
          Start over
        </button>
      ) : (
        <div role="group" aria-label="Start this sample over?">
          <p className="ft-strong">Start this sample over?</p>
          <p className="ft-caption">It goes back to its opening date, and everything done on it is cleared. Other grants aren&apos;t touched.</p>
          <span className="ft-tl__actions">
            <button
              type="button"
              className="ft-btn ft-btn--sm ft-btn--reject"
              disabled={busy}
              onClick={() => void onStartOver().then((done) => done && setAsking(false))}
            >
              Start over
            </button>
            <button ref={cancel} type="button" className="ft-btn ft-btn--sm" disabled={busy} onClick={() => setAsking(false)}>
              Cancel
            </button>
          </span>
        </div>
      )}
    </div>
  );
}

/** The panel itself, for a grant known to be a sample. */
export function TimelinePanel({ grantId }: { grantId: Id }) {
  const api = useApi();
  const refresh = useRefresh();
  const timeline = useTimeline(grantId);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function act(run: () => Promise<unknown>): Promise<void> {
    await attempt(run);
  }

  /** Runs one action, then refetches everything: a move changes the grant's other pages too. */
  async function attempt(run: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setProblem(null);
    try {
      await run();
      await refresh();
      return true;
    } catch (error) {
      setProblem(
        error instanceof SampleRefusalError
          ? error.refusal.message
          : error instanceof ApiError && typeof error.detail === "string"
            ? error.detail
            : "That didn't work. Try again.",
      );
      return false;
    } finally {
      setBusy(false);
    }
  }

  const view = timeline.data;
  return (
    <section className="ft-panel ft-tl" aria-labelledby="tl-heading">
      <div className="ft-panel__head">
        <h2 id="tl-heading" className="ft-heading">
          Sample timeline
        </h2>
      </div>
      {timeline.error && !view ? (
        <p className="ft-error" role="alert">
          Couldn&apos;t load the timeline. It reloads when the window regains focus.
        </p>
      ) : !view ? (
        <p className="ft-empty">Loading…</p>
      ) : (
        <>
          <div className="ft-tl__controls">
            <button
              type="button"
              className="ft-btn ft-btn--main ft-btn--sm"
              disabled={busy || (view.coming_up ?? []).length === 0}
              onClick={() => void act(() => api.moveTimeline(grantId, {}))}
            >
              Next event
            </button>
            <GoToDate now={view.now.now} busy={busy} onGo={(to) => void act(() => api.moveTimeline(grantId, { to }))} />
          </div>
          {problem && (
            <p className="ft-error" role="alert">
              {problem}
            </p>
          )}
          <div className="ft-tl__parts">
            <JustHappened grantId={grantId} played={view.just_happened ?? []} />
            <Now grantId={grantId} view={view} busy={busy} act={act} />
            <ComingUp events={view.coming_up ?? []} finished={view.finished} />
          </div>
          <StartOver busy={busy} onStartOver={() => attempt(() => api.startOver(grantId, true))} />
        </>
      )}
    </section>
  );
}

/** The timeline panel when the grant is a sample grant; nothing for any other grant. */
export function SampleTimeline({ summary }: { summary: GrantSummary }) {
  return summary.grant.sample ? <TimelinePanel grantId={summary.grant.id} /> : null;
}
