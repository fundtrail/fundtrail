"use client";

// The timeline panel on a sample grant's page, and only there (ruling 40,
// issue 165). It plays the sample's timeline; it never edits it. Every date
// comes from the server: the timeline's own now, never the browser's clock.
// Wording is a placeholder until the docs give it. First version, may change.

import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import {
  ApiError,
  describeError,
  SampleRefusalError,
  useApi,
  useCharges,
  useRefresh,
  useTimeline,
  type ArrivalSource,
  type GrantSummary,
  type FtRecord,
  type Id,
  type PlayedEvent,
  type TimelineEvent,
  type TimelineEventKind,
  type TimelineView,
  type UserDelivery,
} from "@/lib/api";
import { date, recordKindLabel } from "@/lib/format";
import { routes } from "@/lib/routes";
import { useGrantDisplayName } from "@/lib/grantName";
import "./timeline.css";
import { Guide } from "./Guide";

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
      <span className="ft-num ft-tl__date">{date(event.at)}</span>
      <span className="ft-strong ft-tl__name">{event.name}</span>
      {event.highlight && <span className="ft-tag ft-tl__highlight">Highlight: {event.highlight}</span>}
      <span className="ft-caption">
        {KIND_WORDS[event.kind]}
        {event.source && <> · {SOURCE_WORDS[event.source]}</>}
      </span>
      {event.note && <span className="ft-caption">{event.note}</span>}
    </>
  );
}

/** How many events show on the trail on each side of now. The rest open in place with Show all. */
const FEW = 2;

/** What the agent wrote from one played event, as kinds and counts. */
function agentSummary(played: PlayedEvent): string {
  const records = played.agent_records ?? [];
  if (records.length === 0) return "The agent wrote nothing from it yet.";
  const counts = new Map<string, number>();
  for (const r of records) counts.set(recordKindLabel(r.data.kind), (counts.get(recordKindLabel(r.data.kind)) ?? 0) + 1);
  const parts = [...counts].map(([label, n]) => (n > 1 ? `${label} (${n})` : label));
  return `The agent wrote: ${parts.join(", ")}.`;
}

/** A decision the sample accountant made, in a few words. */
function decisionWords(record: FtRecord): string {
  const { data } = record;
  if (data.kind === "confirmation") {
    const n = data.record_ids.length;
    return `${data.decision === "rejected" ? "rejected" : "confirmed"} ${n} ${n === 1 ? "record" : "records"}`;
  }
  return recordKindLabel(data.kind).toLowerCase();
}

/**
 * Who delivered an item the user was to deliver, as the server says it. The
 * user is credited only when the flag is explicitly false and the item isn't
 * still waiting in Now.
 */
function DeliveredBy({ played, waiting }: { played: PlayedEvent; waiting: Set<Id> }) {
  if (played.event.kind !== "user_delivery") return null;
  if (played.delivered_by_sample_accountant === true) {
    return <span className="ft-tag ft-tl__delivered">Delivered for you by the sample accountant</span>;
  }
  if (played.delivered_by_sample_accountant === false && !waiting.has(played.event.id)) {
    return <span className="ft-caption">Delivered by you.</span>;
  }
  return null;
}

/** A toggle that shows the events kept off the trail, in place. */
function ShowAll({ open, count, controls, onToggle }: { open: boolean; count: number; controls: string; onToggle: () => void }) {
  return (
    <button type="button" className="ft-tl__toggle" aria-expanded={open} aria-controls={controls} onClick={onToggle}>
      {open ? "Show fewer" : `Show all ${count}`}
    </button>
  );
}

/** The tag on a result loaded from a prerun, saying which kind it came from. */
function loadedTag(expected: boolean | null | undefined): string {
  return expected ? "Loaded from the expected prerun" : "Loaded from the prerun";
}

function JustHappened({
  grantId,
  played,
  waiting,
  expected,
}: {
  grantId: Id;
  played: PlayedEvent[];
  waiting: Set<Id>;
  expected?: boolean | null;
}) {
  // The grant's charges, to name each charge link by its ledger line. The page loads the same list.
  const charges = useCharges(grantId).data;
  const [open, setOpen] = useState(false);
  const listId = useId();
  // The last few sit on the trail; earlier ones open in place.
  const hidden = open ? 0 : Math.max(0, played.length - FEW);
  return (
    <section className="ft-tl__part ft-tl__part--past" aria-labelledby="tl-just" style={{ flexGrow: Math.max(1, played.length - hidden) }}>
      <div className="ft-tl__label">
        <h3 id="tl-just" className="ft-label">
          Just happened
        </h3>
        {played.length > FEW && <ShowAll open={open} count={played.length} controls={listId} onToggle={() => setOpen(!open)} />}
      </div>
      {played.length === 0 ? (
        <div className="ft-tl__row">
          <p className="ft-caption ft-tl__ev ft-tl__ev--past ft-tl__ev--empty">Nothing yet.</p>
        </div>
      ) : (
        <ul id={listId} className="ft-tl__list ft-tl__row">
          {played.map((p, i) => (
            <li key={p.event.id} className={`ft-tl__item ft-tl__ev ft-tl__ev--past${i < hidden ? " ft-tl__tail" : ""}`}>
              <EventLine event={p.event} />
              {/* A result loaded from the prerun is marked, so it never passes for live work. */}
              {p.loaded && <span className="ft-tag ft-tl__loaded">{loadedTag(expected)}</span>}
              {/* Who delivered an item the user was to deliver (rulings 44 and 52). */}
              <DeliveredBy played={p} waiting={waiting} />
              <span className="ft-tl__wrote">{agentSummary(p)}</span>
              {(p.scripted_decisions ?? []).length > 0 && (
                <ul className="ft-tl__decisions" aria-label="The sample accountant's decisions">
                  {(p.scripted_decisions ?? []).map((d) => (
                    <li key={d.id} className="ft-caption">
                      The sample accountant: {decisionWords(d)}, {date(d.written_at)}
                    </li>
                  ))}
                </ul>
              )}
              {(p.charge_ids ?? []).map((chargeId, i, all) => {
                // The link reads its ledger line once the charges are loaded; what it says aloud starts with what it shows.
                const line = charges?.find((r) => r.charge.id === chargeId)?.charge.ledger_line_id;
                const from = `the charge from ${p.event.name}${all.length > 1 ? ` (${i + 1} of ${all.length})` : ""}`;
                return (
                  <Link
                    key={chargeId}
                    className="ft-link ft-tl__open"
                    href={routes.charge(grantId, chargeId)}
                    aria-label={line ? `${line}, open ${from}` : `Open ${from}`}
                  >
                    {line ?? "Open the charge"}
                  </Link>
                );
              })}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Opens a file's link in a new tab: a signed link is on another origin, where a download name is ignored. */
function openFile(url: string, name: string) {
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.target = "_blank";
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
          onClick={() => void act(async () => openFile((await api.deliveryFileUrl(grantId, event.id)).url, event.name))}
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
    <section className="ft-tl__part ft-tl__part--now" aria-labelledby="tl-now">
      <div className="ft-tl__label" aria-hidden="true" />
      <div className="ft-tl__row">
        <div className="ft-tl__ev ft-tl__ev--now">
          <p className="ft-tl__nowline">
            <span id="tl-now" role="heading" aria-level={3} className="ft-tl__nowtag">
              Now
            </span>{" "}
            <span className="ft-num ft-strong">{date(now.now)}</span>
          </p>
          {now.stopped_on && (
            <p className="ft-tl__stopped">
              stopped on <span className="ft-strong ft-tl__name">{now.stopped_on.name}</span>
            </p>
          )}
          {view.catching_up && <p className="ft-caption">The agent is still catching up on what arrived.</p>}
          {deliveries.length > 0 && (
            <ul className="ft-tl__list ft-tl__deliveries" aria-label="For you to deliver">
              {deliveries.map((d) => (
                <Delivery key={d.event.id} grantId={grantId} delivery={d} busy={busy} act={act} />
              ))}
            </ul>
          )}
          <p className="ft-tl__waiting">
            {now.waiting_on_problem_list > 0 ? (
              <Link className="ft-link" href={routes.problemList(grantId)}>
                {now.waiting_on_problem_list} waiting on the problem list
              </Link>
            ) : (
              <span className="ft-caption">Nothing waiting on the problem list.</span>
            )}
          </p>
        </div>
      </div>
    </section>
  );
}

function ComingUp({ events, finished }: { events: TimelineEvent[]; finished: boolean }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const fewer = useRef<HTMLButtonElement>(null);
  const more = useRef<HTMLButtonElement>(null);
  const moved = useRef(false);
  // Focus follows the toggle as it moves between the closing item and the label.
  useEffect(() => {
    if (!moved.current) return;
    (open ? fewer : more).current?.focus();
  }, [open]);
  function toggle() {
    moved.current = true;
    setOpen(!open);
  }
  // The next few sit on the trail; one closing item counts the rest and opens them in place.
  const rest = events.slice(FEW);
  const restHighlights = rest.filter((e) => e.highlight).length;
  const last = rest[rest.length - 1];
  const onTrail = open ? events.length : Math.min(events.length, FEW);
  return (
    <section className="ft-tl__part ft-tl__part--next" aria-labelledby="tl-coming" style={{ flexGrow: Math.max(1, onTrail + (rest.length > 0 && !open ? 1 : 0)) }}>
      <div className="ft-tl__label">
        <h3 id="tl-coming" className="ft-label">
          Coming up
        </h3>
        {open && (
          <button ref={fewer} type="button" className="ft-tl__toggle" aria-expanded="true" aria-controls={listId} onClick={toggle}>
            Show fewer
          </button>
        )}
      </div>
      {events.length === 0 ? (
        <div className="ft-tl__row">
          <p className="ft-caption ft-tl__ev ft-tl__ev--next ft-tl__ev--empty">{finished ? "The timeline has played to its end." : "Nothing else is coming up."}</p>
        </div>
      ) : (
        <div className="ft-tl__row">
          <ol id={listId} className="ft-tl__list ft-tl__row" style={{ flexGrow: onTrail }}>
            {events.map((e, i) => (
              <li key={e.id} className={`ft-tl__item ft-tl__ev ft-tl__ev--next${!open && i >= FEW ? " ft-tl__tail" : ""}`}>
                <EventLine event={e} />
              </li>
            ))}
          </ol>
          {rest.length > 0 && !open && (
            <div className="ft-tl__ev ft-tl__ev--next ft-tl__ev--more">
              {last && <span className="ft-num ft-tl__date">through {date(last.at)}</span>}
              <button ref={more} type="button" className="ft-tl__more" aria-expanded="false" aria-controls={listId} onClick={toggle}>
                {rest.length} more {rest.length === 1 ? "event" : "events"}
              </button>
              {restHighlights > 0 && (
                <span className="ft-caption">
                  {restHighlights} {restHighlights === 1 ? "highlight" : "highlights"}
                </span>
              )}
            </div>
          )}
        </div>
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

/**
 * Go to a date. While the server says the timeline can't move, Go is
 * unavailable: it sends nothing, and the server's reason shows beside it as
 * its description.
 */
function GoToDate({ now, busy, onGo, reason }: { now: string; busy: boolean; onGo: (to: string) => void; reason?: { id: string; text: string } }) {
  const id = useId();
  const [value, setValue] = useState("");
  const min = dayAfter(now);
  function submit(event: FormEvent) {
    event.preventDefault();
    if (reason) return;
    if (value && value >= min) {
      onGo(`${value}T00:00:00Z`);
      // The field starts empty again after a move.
      setValue("");
    }
  }
  return (
    <form className="ft-tl__goto" onSubmit={submit}>
      <label htmlFor={id} className="ft-label">
        Go to a date
      </label>
      <input id={id} type="date" min={min} value={value} onChange={(e) => setValue(e.target.value)} required />
      <button
        type="submit"
        className="ft-btn ft-btn--sm"
        disabled={busy || !value || value < min}
        aria-disabled={reason ? true : undefined}
        aria-describedby={reason?.id}
      >
        Go
      </button>
      {reason && (
        <span id={reason.id} className="ft-tl__reason">
          {reason.text}
        </span>
      )}
    </form>
  );
}

/**
 * Asked before a move without skipping that would take a prerun grant off its
 * run-through: staying is the default, and leaving makes the move.
 */
function LeaveConfirm({ busy, onLeave, onStay }: { busy: boolean; onLeave: () => void; onStay: () => void }) {
  const stay = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    stay.current?.focus();
  }, []);
  return (
    <div className="ft-tl__startover" role="group" aria-label="Leave the prerun?">
      <div>
        <p className="ft-strong">Leave the prerun?</p>
        <p className="ft-caption">
          This move passes a step of the sample&apos;s script that hasn&apos;t been made, so it differs from the script. The grant leaves the
          prerun, and from here the agent works live, which takes minutes for each file. Skip the human steps to stay on it.
        </p>
      </div>
      <span className="ft-tl__actions">
        <button ref={stay} type="button" className="ft-btn ft-btn--sm" disabled={busy} onClick={onStay}>
          Stay on the prerun
        </button>
        <button type="button" className="ft-btn ft-btn--sm ft-btn--reject" disabled={busy} onClick={onLeave}>
          Leave the prerun
        </button>
      </span>
    </div>
  );
}

/** Start over's confirm step, under the controls while it's asked. */
function StartOverConfirm({ busy, onStartOver, onCancel }: { busy: boolean; onStartOver: () => Promise<boolean>; onCancel: () => void }) {
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    cancel.current?.focus();
  }, []);
  return (
    <div className="ft-tl__startover" role="group" aria-label="Start this sample over?">
      <div>
        <p className="ft-strong">Start this sample over?</p>
        <p className="ft-caption">It goes back to its opening date, and everything done on it is cleared. Other grants aren&apos;t touched.</p>
      </div>
      <span className="ft-tl__actions">
        <button
          type="button"
          className="ft-btn ft-btn--sm ft-btn--reject"
          disabled={busy}
          onClick={() => void onStartOver().then((done) => done && onCancel())}
        >
          Start over
        </button>
        <button ref={cancel} type="button" className="ft-btn ft-btn--sm" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </span>
    </div>
  );
}

/**
 * The panel itself, for a grant known to be a sample, folded to a quiet line:
 * where the clock stands, what it stopped on (with its prerun mark and the
 * sample accountant's decisions, decision 0027), what waits on the problem
 * list, what comes next, Next event, and More, which opens everything else in
 * place: the other controls and the trail with every mark. A refused move, a
 * load error, catching up and the run-through note show while folded too.
 */
export function TimelinePanel({ grantId, workspaceId }: { grantId: Id; workspaceId?: Id }) {
  const grantName = useGrantDisplayName();
  const api = useApi();
  const refresh = useRefresh();
  const timeline = useTimeline(grantId);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<{ text: string; grant: GrantSummary | null } | null>(null);
  // Ruling 47: Next event and Go to a date can let the sample accountant do the human steps.
  const [skip, setSkip] = useState(false);
  // Start over asks first, under the controls.
  const [asking, setAsking] = useState(false);
  // A move that would take a prerun grant off its run-through asks first, and waits here.
  const [leaving, setLeaving] = useState<(() => Promise<unknown>) | null>(null);
  // Everything but Next event stays folded until More.
  const [trailOpen, setTrailOpen] = useState(false);
  const moreRef = useRef<HTMLButtonElement>(null);
  const trailId = useId();
  const skipId = useId();
  const highlightHintId = useId();
  const moveReasonId = useId();
  const goReasonId = useId();
  const highlightReasonId = useId();

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
          ? { text: error.refusal.message, grant: error.refusal.grant ?? null }
          : { text: error instanceof ApiError && typeof error.detail === "string" ? error.detail : "That didn't work. Try again.", grant: null },
      );
      return false;
    } finally {
      setBusy(false);
    }
  }

  const view = timeline.data;
  // The guide takes the folded line's place on a sample with highlights.
  const guided = !!view?.highlight_total;
  const toDeliver = (view?.now.deliveries ?? []).filter((d) => !d.delivered).length;
  // Ruling 79: when the server says a move can't happen now, the control sends nothing and shows why, in the server's words.
  const moveReason = view?.move_unavailable_reason || null;
  const highlightReason = view?.next_highlight_unavailable_reason || null;

  /** A plain move to `to` on a grant on its run-through that would leave it asks first; any other move goes. */
  function move(to: string | undefined, run: () => Promise<unknown>) {
    const leavesAt = view?.on_run_through ? view.leaves_run_through_at : null;
    if (!skip && leavesAt && to && Date.parse(to) >= Date.parse(leavesAt)) {
      setLeaving(() => run);
      return;
    }
    void act(run);
  }

  const nextEvent = view && (
    <button
      type="button"
      className="ft-btn ft-btn--sm"
      disabled={busy || (view.coming_up ?? []).length === 0}
      aria-disabled={moveReason ? true : undefined}
      aria-describedby={moveReason ? moveReasonId : undefined}
      onClick={() => {
        if (moveReason) return;
        move((view.coming_up ?? [])[0]?.at, () => api.moveTimeline(grantId, skip ? { skip_human_steps: true } : {}));
      }}
    >
      Next event
    </button>
  );
  // A grant loaded from a prerun has Next highlight beside Next event; any other keeps it under More.
  const prerunGrant = view?.on_run_through === true || view?.on_run_through === false;
  const nextHighlight = view && (
    <>
      {/* Ruling 77: the server finds the next highlight, does the steps before it, and leaves the highlight's own step to the user. */}
      <span className="ft-tl__hinted">
        <button
          type="button"
          className="ft-btn ft-btn--sm"
          aria-describedby={highlightReason ? highlightReasonId : highlightHintId}
          disabled={busy}
          aria-disabled={highlightReason ? true : undefined}
          onClick={() => {
            if (highlightReason) return;
            void act(() => api.moveTimeline(grantId, { next_highlight: true }));
          }}
        >
          Next highlight
        </button>
        <span id={highlightHintId} className="ft-caption">
          Moves to the next highlight; the steps before it are done for you, the highlight&apos;s own step is yours.
        </span>
        {highlightReason && (
          <span id={highlightReasonId} className="ft-tl__reason">
            {highlightReason}
          </span>
        )}
      </span>
    </>
  );
  const otherControls = view && (
    <>
      {guided && nextEvent}
      {!prerunGrant && !guided && nextHighlight}
      <GoToDate
        now={view.now.now}
        busy={busy}
        reason={moveReason ? { id: goReasonId, text: moveReason } : undefined}
        onGo={(to) => move(to, () => api.moveTimeline(grantId, skip ? { to, skip_human_steps: true } : { to }))}
      />
      <span className="ft-tl__skip">
        <input id={skipId} type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} />
        <label htmlFor={skipId}>Skip the human steps</label>
      </span>
      {!asking && (
        <button type="button" className="ft-btn ft-btn--sm ft-tl__quiet" disabled={busy} onClick={() => setAsking(true)}>
          Start over
        </button>
      )}
    </>
  );

  // The event the clock stopped on, as the last move played it, for its marks on the folded line.
  const stop = view?.now.stopped_on ? (view.just_happened ?? []).find((p) => p.event.id === view.now.stopped_on?.id) : undefined;
  const decisions = stop?.scripted_decisions ?? [];
  const next = (view?.coming_up ?? [])[0];

  // The guide (where you are among the highlights, your step, one main button) takes the
  // folded line's place on a sample with highlights; More opens everything else.
  const moreButton = view && (
    <button
      ref={moreRef}
      type="button"
      className="ft-btn ft-btn--sm"
      aria-expanded={trailOpen}
      aria-controls={trailOpen ? trailId : undefined}
      onClick={() => setTrailOpen(!trailOpen)}
    >
      {trailOpen ? "Less" : "More"}
    </button>
  );

  return (
    <section className="ft-tl" aria-labelledby="tl-heading" data-compact="" aria-busy={busy || undefined}>
      {guided && view && (
        <>
          <span id="tl-heading" role="heading" aria-level={2} className="ft-guide__heading">
            Sample timeline
          </span>
          <Guide
            grantId={grantId}
            workspaceId={workspaceId}
            view={view}
            busy={busy}
            menu={<span className="ft-guide__menu">{moreButton}</span>}
            onNextHighlight={() => void act(() => api.moveTimeline(grantId, { next_highlight: true }))}
            onDeliver={(eventId) => void act(() => api.deliverForMe(grantId, eventId))}
            onGetFile={(eventId) =>
              void act(async () => openFile((await api.deliveryFileUrl(grantId, eventId)).url, view.highlight_event?.name ?? "file"))
            }
            onCloseoutMove={(to) => void act(() => api.moveTimeline(grantId, { to, skip_human_steps: true }))}
          />
        </>
      )}
      {!guided && (
      <div className="ft-tl__line">
        <span className="ft-tl__dot" aria-hidden="true" />
        <p className="ft-tl__where">
          <span id="tl-heading" role="heading" aria-level={2} className="ft-strong">
            Sample timeline
          </span>
          {view && (
            <>
              <span className="ft-tl__sep">·</span>
              <span className="ft-num">{date(view.now.now)}</span>
              {view.now.stopped_on && (
                <>
                  <span className="ft-tl__sep">·</span>
                  <span className="ft-tl__where-stop">
                    stopped on <span className="ft-id">{view.now.stopped_on.name}</span>
                    {view.now.stopped_on.highlight && <span className="ft-tl__flag">{view.now.stopped_on.highlight}</span>}
                  </span>
                </>
              )}
              {view.now.waiting_on_problem_list > 0 && (
                <>
                  <span className="ft-tl__sep">·</span>
                  <Link className="ft-link" href={routes.problemList(grantId)}>
                    {view.now.waiting_on_problem_list} waiting on the problem list
                  </Link>
                </>
              )}
              {toDeliver > 0 && !trailOpen && (
                <>
                  <span className="ft-tl__sep">·</span>
                  <span>{toDeliver} for you to deliver</span>
                </>
              )}
              {view.catching_up && !trailOpen && (
                <>
                  <span className="ft-tl__sep">·</span>
                  <span className="ft-caption">The agent is still catching up on what arrived.</span>
                </>
              )}
            </>
          )}
        </p>
        {view && (
          <span className="ft-tl__lineActions">
            {nextEvent}
            {prerunGrant && nextHighlight}
            <button
              ref={moreRef}
              type="button"
              className="ft-btn ft-btn--sm"
              aria-expanded={trailOpen}
              aria-controls={trailOpen ? trailId : undefined}
              onClick={() => setTrailOpen(!trailOpen)}
            >
              {trailOpen ? "Less" : "More"}
            </button>
          </span>
        )}
        {moveReason && (
          <p id={moveReasonId} className="ft-tl__reason ft-tl__reason--line">
            {moveReason}
          </p>
        )}
      </div>
      )}
      {leaving && (
        <LeaveConfirm
          busy={busy}
          onStay={() => setLeaving(null)}
          onLeave={() => {
            const run = leaving;
            setLeaving(null);
            void act(run);
          }}
        />
      )}
      {/* Folded, the stop's marks and what comes next, on a second quiet line. */}
      {view && !trailOpen && !guided && (stop?.loaded || decisions.length > 0 || next || view.finished) && (
        <ul className="ft-tl__also" aria-label="About the stop and what comes next">
          {stop?.loaded && (
            <li>
              <span className="ft-tag ft-tl__loaded">{loadedTag(view.expected_prerun)}</span>
            </li>
          )}
          {decisions.map((d) => (
            <li key={d.id} className="ft-caption">
              The sample accountant: {decisionWords(d)}, {date(d.written_at)}
            </li>
          ))}
          {next ? (
            <li>
              <span className="ft-label">Coming up</span> <span className="ft-num">{date(next.at)}</span> · <span className="ft-id">{next.name}</span>
              {next.highlight && <span className="ft-tl__flag ft-tl__flag--next">{next.highlight}</span>}
            </li>
          ) : (
            view.finished && <li className="ft-caption">The timeline has played to its end.</li>
          )}
        </ul>
      )}
      {timeline.error && !view ? (
        <p className="ft-error" role="alert">
          {describeError(timeline.error).message}
        </p>
      ) : !view ? (
        <p className="ft-empty">Loading…</p>
      ) : (
        <>
          {problem && (
            <p className="ft-error ft-tl__note" role="alert">
              {problem.text}
              {/* A refused move names the sample that's still working. */}
              {problem.grant && (
                <>
                  {" "}
                  <Link className="ft-link" href={routes.grant(problem.grant.grant.id)}>
                    Open {grantName(problem.grant)}
                  </Link>
                </>
              )}
            </p>
          )}
          {view.expected_prerun && (
            <p className="ft-caption ft-tl__note">
              This grant loads an expected prerun: the records we expect the agent to write, prepared ahead of time, not the agent&apos;s output.
            </p>
          )}
          {view.on_run_through === false && <p className="ft-caption ft-tl__note">This grant is off the run-through: from here the agent works live.</p>}
          {trailOpen && (
            <div
              id={trailId}
              className="ft-tl__body"
              onKeyDown={(e) => {
                // Escape folds it again and returns focus to More.
                if (e.key === "Escape") {
                  setTrailOpen(false);
                  moreRef.current?.focus();
                }
              }}
            >
              <div className="ft-tl__controls">{otherControls}</div>
              {asking && <StartOverConfirm busy={busy} onStartOver={() => attempt(() => api.startOver(grantId, true))} onCancel={() => setAsking(false)} />}
              <div className="ft-tl__track">
                <JustHappened
                  grantId={grantId}
                  played={view.just_happened ?? []}
                  waiting={new Set((view.now.deliveries ?? []).filter((d) => !d.delivered).map((d) => d.event.id))}
                  expected={view.expected_prerun}
                />
                <Now grantId={grantId} view={view} busy={busy} act={act} />
                <ComingUp events={view.coming_up ?? []} finished={view.finished} />
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}

/** The timeline panel when the grant is a sample grant; nothing for any other grant. */
export function SampleTimeline({ summary }: { summary: GrantSummary }) {
  return summary.grant.sample ? <TimelinePanel grantId={summary.grant.id} workspaceId={summary.grant.workspace_id} /> : null;
}
