// Sample grants in fake mode: the Sample dropdown's choices, opening a sample,
// and a sample grant's timeline (ruling 40). Shared base (the screens
// foundation): the setup screens and the timeline panel both read it.
//
// Everything here is a placeholder until the sample packs and the docs give the
// words. The fake's timeline is the contract's sample grant played as events:
// the two uploads are items the user delivers, and the Gmail and Drive files
// and the two ledger lines arrive. A sample opens at the start of its
// timeline: its first event, played. The fake's own sample grant starts where
// the rest of the fake stands, at FAKE_NOW, with every event played and both
// uploads on file; Start over takes it back to its first event. A sample grant
// opened in fake mode starts at its first event. The fake has no checks or
// agent, so the grant's other pages don't follow the timeline.

import { ApiError, SampleRefusalError, type ApiClient } from "../client";
import type { FileLink, FtRecord, Grant, GrantSample, GrantSummary, Id, IsoDatetime, PlayedEvent, SampleOption, TimelineEvent, TimelineView } from "../types";
import { SAMPLE_DOCUMENTS } from "./documents";
import { FAKE_NOW, fakeId, sample, served, SAMPLE_GRANT_ID } from "./sample";

/** How the fake marks the contract's sample grant as a sample. */
export const SAMPLE_GRANT_SAMPLE: GrantSample = { sample: "sample-grant", choice: "small_live" };

export const SAMPLE_OPTIONS: SampleOption[] = [
  {
    choice: "small_live",
    name: "Small sample",
    description: "Placeholder: a small synthetic grant. The agent reads each event as you play it.",
    needs_confirm: false,
    available: true,
  },
  {
    choice: "larger_live",
    name: "Larger sample, read live",
    description: "Placeholder: a larger synthetic grant. The agent reads its history first, which takes a while.",
    needs_confirm: true,
    available: true,
  },
  {
    choice: "larger_prerun",
    name: "Larger sample, read ahead",
    description: "Placeholder: the larger grant with its history already read.",
    needs_confirm: false,
    available: false,
    unavailable_reason: "Placeholder: not prepared in fake mode.",
  },
];

/**
 * One way of writing a UTC time, "...Z", as the rest of the fake writes it.
 * The contract's sample writes a ledger line's arrival as "+00:00".
 */
function utc(iso: IsoDatetime): IsoDatetime {
  return iso.endsWith("+00:00") ? `${iso.slice(0, -6)}Z` : iso;
}

/** Placeholder highlight labels for a few of the sample's events (ruling 58). */
const HIGHLIGHTS: Record<string, string> = {
  "event-file-sequencing-statement": "A bill by email",
  "event-chg-l-1002": "Work after the end date",
  "event-file-extension-notice": "An extension notice",
};

/**
 * Ruling 77: a highlight's own step carries that highlight's label, and Next
 * highlight leaves it for the user. Here, confirming the extension is the "An
 * extension notice" highlight's own step. Keyed by the step: a delivery's event
 * ID, or a decision's record ID.
 */
export const STEP_HIGHLIGHTS: Record<string, string> = {
  "rec-confirm-extension": "An extension notice",
};

/** The contract's sample grant as timeline events, in date order, with placeholder highlights. */
export function sampleEvents(): TimelineEvent[] {
  const files: TimelineEvent[] = sample.files.map((f) => ({
    id: `event-${f.id}`,
    at: utc(f.arrived_at),
    kind: f.source === "upload" ? "user_delivery" : "arrival",
    source: f.source,
    name: f.name,
    note: null,
    charge_id: null,
    file_id: f.id,
  }));
  const lines: TimelineEvent[] = sample.charges.map((c) => ({
    id: `event-${c.id}`,
    at: utc(c.arrived_at),
    kind: "arrival",
    source: "ledger",
    name: c.ledger_line_id,
    note: null,
    charge_id: c.id,
    file_id: null,
  }));
  return [...files, ...lines]
    .map((e) => ({ ...e, highlight: HIGHLIGHTS[e.id] ?? null }))
    .sort((a, b) => time(a.at) - time(b.at));
}

const time = (iso: IsoDatetime) => new Date(iso).getTime();

/** What the agent wrote from an event: the sample's agent records written at that moment. */
function played(event: TimelineEvent): PlayedEvent {
  const agentRecords: FtRecord[] = sample.records.filter((r) => r.author === "agent" && time(r.written_at) === time(event.at));
  const fromLinks = agentRecords.flatMap((r) => (r.data.kind === "link" ? [r.data.charge_id] : []));
  const chargeIds = [...new Set([...(event.charge_id ? [event.charge_id] : []), ...fromLinks])];
  return { event, agent_records: agentRecords, charge_ids: chargeIds };
}

interface TimelineState {
  now: IsoDatetime;
  played: Set<Id>;
  delivered: Map<Id, IsoDatetime>;
  justHappened: Id[];
  stoppedOn: Id | null;
  /** The sample accountant's decisions in the last move, by the event they follow. */
  scripted: Map<Id, FtRecord[]>;
  /** Items the sample accountant delivered for the user. */
  byAccountant: Set<Id>;
  /** The sample's own accountant decisions made so far, by record ID. */
  decided: Set<Id>;
  /**
   * Scripted steps held for the user (ruling 77): a highlight's own steps that a
   * Next highlight move left, and sign-offs, which skipping never makes on a
   * user's grant. By step ID: a delivery's event ID, or a decision's record ID.
   */
  held: Set<Id>;
}

function emptyState(at: IsoDatetime): TimelineState {
  return { now: at, played: new Set(), delivered: new Map(), justHappened: [], stoppedOn: null, scripted: new Map(), byAccountant: new Set(), decided: new Set(), held: new Set() };
}

/** A sample at the start of its timeline: its first event played. */
function startState(events: TimelineEvent[]): TimelineState {
  const state = emptyState(events[0].at);
  playTo(events, state, events[0].at);
  return state;
}

/** When a sample opens: its first event. */
export function sampleStartsAt(): IsoDatetime {
  return sampleEvents()[0].at;
}

/** The sample grant as the rest of the fake shows it: everything up to FAKE_NOW played, both uploads on file. */
function sampleGrantState(events: TimelineEvent[]): TimelineState {
  const state = emptyState(FAKE_NOW);
  const past = events.filter((e) => time(e.at) <= time(FAKE_NOW));
  for (const e of past) {
    state.played.add(e.id);
    if (e.kind === "user_delivery") state.delivered.set(e.id, e.at);
  }
  // The decisions the rest of the fake shows as made by FAKE_NOW (the award terms confirmed).
  for (const r of sample.records) if (r.author === "user" && time(r.written_at) <= time(FAKE_NOW)) state.decided.add(r.id);
  const last = past.filter((e) => e.kind !== "user_delivery").at(-1);
  state.justHappened = last ? [last.id] : [];
  state.stoppedOn = last?.id ?? null;
  return state;
}

/** Ruling 86: the highlight's own step due and unmade that Next highlight waits for, in plain words. */
function ownStepWaiting(events: TimelineEvent[], state: TimelineState, marks: Record<string, string>): string | null {
  const step = scriptedSteps(events).find(
    (s) => !!marks[s.id] && s.decision?.data.kind !== "sign_off" && !isDone(s, state) && time(s.at) <= time(state.now),
  );
  if (!step) return null;
  const what = step.delivery
    ? `Bring in ${step.delivery.name}`
    : step.decision?.data.kind === "confirmation"
      ? "Confirm the terms"
      : "Make this highlight's decision";
  return `${what} first: that's this highlight's step.`;
}

function view(events: TimelineEvent[], state: TimelineState, problemRows: number, marks: Record<string, string> = {}): TimelineView {
  const byId = new Map(events.map((e) => [e.id, e]));
  const deliveries = events
    .filter((e) => e.kind === "user_delivery" && state.played.has(e.id) && !state.delivered.has(e.id))
    .map((event) => ({ event, delivered: false, delivered_at: null }));
  const comingUp = events.filter((e) => !state.played.has(e.id));
  return {
    just_happened: state.justHappened.map((id) => ({
      ...played(byId.get(id)!),
      scripted_decisions: state.scripted.get(id) ?? [],
      loaded: false,
      delivered_by_sample_accountant: state.byAccountant.has(id),
    })),
    now: {
      now: state.now,
      stopped_on: state.stoppedOn ? byId.get(state.stoppedOn) ?? null : null,
      deliveries,
      // Placeholder: the fake's problem list once the sample reaches FAKE_NOW.
      waiting_on_problem_list: time(state.now) >= time(FAKE_NOW) ? problemRows : 0,
    },
    coming_up: comingUp,
    finished: comingUp.length === 0 && deliveries.length === 0,
    catching_up: false,
    // The fake's samples are read live, so there's no run-through.
    on_run_through: null,
    // Ruling 86 only; the fake has never given a reason for no highlight being left.
    next_highlight_unavailable_reason: ownStepWaiting(events, state, marks),
  };
}

/** Plays every event up to `to`. Items to deliver become due; arrivals are played. */
function playTo(events: TimelineEvent[], state: TimelineState, to: IsoDatetime) {
  const reached = events.filter((e) => !state.played.has(e.id) && time(e.at) <= time(to));
  for (const e of reached) state.played.add(e.id);
  state.justHappened = reached.filter((e) => e.kind !== "user_delivery").map((e) => e.id);
  state.stoppedOn = reached.filter((e) => time(e.at) === time(to)).at(-1)?.id ?? null;
  state.now = to;
  state.scripted = new Map();
}

/** One scripted human step: delivering an item the user was to deliver, or one of the sample's own accountant decisions. */
interface Step {
  id: Id;
  at: IsoDatetime;
  delivery?: TimelineEvent;
  decision?: FtRecord;
}

function scriptedSteps(events: TimelineEvent[]): Step[] {
  const deliveries: Step[] = events.filter((e) => e.kind === "user_delivery").map((e) => ({ id: e.id, at: e.at, delivery: e }));
  const decisions: Step[] = sample.records.filter((r) => r.author === "user").map((r) => ({ id: r.id, at: r.written_at, decision: r }));
  return [...deliveries, ...decisions].sort((a, b) => time(a.at) - time(b.at));
}

function isDone(step: Step, state: TimelineState): boolean {
  return step.delivery ? state.delivered.has(step.id) : state.decided.has(step.id);
}

/**
 * Skipping the human steps on one move from `from` to the timeline's now, as
 * the backend's player does (ruling 77 with its amendment).
 *
 * - The sample accountant makes the scripted steps due during this move: it
 *   delivers what was the user's to deliver (listed under Just happened, marked
 *   delivered_by_sample_accountant) and makes the sample's own decisions.
 * - A plain, non-skipping move queues nothing: a step it passed stays the
 *   user's, and a later skipping move doesn't make it.
 * - On a Next highlight move to highlight H, H's own steps (marked with its
 *   label) are held for the user, not made. A sign-off is always held: skipping
 *   never makes it on a user's grant.
 * - A later skipping move other than Next highlight makes held steps, except
 *   a sign-off. Next highlight never makes held steps.
 *
 * Ruling 55: each decision is listed once, under the latest event this move
 * played or delivered at or before its time, or else under the move's first
 * event, never under an earlier move's delivery.
 *
 * The fake only lists those decisions; it doesn't carry them out. It has no
 * checks, so the grant's terms, problem list and records stay as they are.
 */
function skipHumanSteps(
  events: TimelineEvent[],
  state: TimelineState,
  marks: Record<string, string>,
  from: IsoDatetime,
  nextHighlight?: string | null,
) {
  const inThisMove = (step: Step) => time(step.at) >= time(from) && time(step.at) <= time(state.now);
  const made: Step[] = [];
  for (const step of scriptedSteps(events)) {
    if (isDone(step, state)) continue;
    const signOff = step.decision?.data.kind === "sign_off";
    // On a Next highlight move, every highlight's own step is held (ruling 86).
    const ownStep = !!nextHighlight && !!marks[step.id];
    if (inThisMove(step) && (signOff || ownStep)) {
      state.held.add(step.id);
      continue;
    }
    const madeNow = inThisMove(step) && !state.held.has(step.id);
    const heldMadeNow = !nextHighlight && state.held.has(step.id) && !signOff;
    if (madeNow || heldMadeNow) {
      state.held.delete(step.id);
      made.push(step);
    }
  }
  for (const step of made) {
    if (step.delivery) {
      state.delivered.set(step.id, step.at);
      state.byAccountant.add(step.id);
      if (!state.justHappened.includes(step.id)) state.justHappened.push(step.id);
    }
  }
  // This move's events, in date order: what it played and what it delivered.
  const thisMove = events.filter((e) => state.justHappened.includes(e.id));
  for (const step of made) {
    const decision = step.decision;
    if (!decision) continue;
    const before = (e: TimelineEvent) => time(e.at) <= time(decision.written_at);
    let on: TimelineEvent | undefined = thisMove.filter(before).at(-1) ?? thisMove[0];
    if (!on) {
      // Nothing happened in this move: the latest arrival before it, never an earlier move's delivery.
      on = events.filter((e) => e.kind !== "user_delivery" && state.played.has(e.id) && before(e)).at(-1);
      if (!on) continue;
      state.justHappened.push(on.id);
    }
    state.decided.add(decision.id);
    state.scripted.set(on.id, [...(state.scripted.get(on.id) ?? []), decision]);
  }
  // In date order, as the server sends them.
  const at = new Map(events.map((e) => [e.id, time(e.at)]));
  state.justHappened.sort((a, b) => at.get(a)! - at.get(b)!);
}

function dataUrl(text: string, mediaType: string): string {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return `data:${mediaType};charset=utf-8;base64,${btoa(binary)}`;
}

export function samplesFake(hooks: {
  /** Serves a sample grant opened in fake mode on the grant pages. */
  addGrant(grant: Grant): void;
  /** The summary the grant pages show for it. */
  summaryOf(grant: Grant): GrantSummary;
  /** How many rows the sample grant's problem list has. */
  problemRows: number;
  /** Which scripted steps are a highlight's own (ruling 77); STEP_HIGHLIGHTS by default. */
  stepHighlights?: Record<string, string>;
}): Pick<ApiClient, "listSamples" | "createSample" | "getTimeline" | "moveTimeline" | "startOver" | "deliverForMe" | "deliveryFileUrl"> {
  const events = sampleEvents();
  const stepHighlights = hooks.stepHighlights ?? STEP_HIGHLIGHTS;
  const timelines = new Map<Id, { state: TimelineState }>([[SAMPLE_GRANT_ID, { state: sampleGrantState(events) }]]);
  const notASample = () => served<TimelineView>(undefined);
  const show = (grantId: Id) =>
    served(view(events, timelines.get(grantId)!.state, grantId === SAMPLE_GRANT_ID ? hooks.problemRows : 0, stepHighlights));

  return {
    listSamples: () => served(SAMPLE_OPTIONS),
    createSample: (workspaceId, body) => {
      const option = SAMPLE_OPTIONS.find((o) => o.choice === body.choice);
      if (!option) return Promise.reject(new ApiError(422, "Unknown sample."));
      if (!option.available) return Promise.reject(new ApiError(409, option.unavailable_reason ?? "This sample isn't available."));
      if (option.needs_confirm && !body.confirmed) {
        return Promise.reject(
          new SampleRefusalError({ reason: "needs_confirm", message: "Placeholder: this sample takes a while to read. Confirm to open it.", grant: null }),
        );
      }
      const grant: Grant = {
        id: fakeId("grant"),
        workspace_id: workspaceId,
        funder: "NSF",
        award_number: null,
        title: null,
        clock_now: events[0].at,
        sample: { sample: "sample-grant", choice: body.choice },
      };
      hooks.addGrant(grant);
      timelines.set(grant.id, { state: startState(events) });
      return served(hooks.summaryOf(grant));
    },
    getTimeline: (grantId) => (timelines.has(grantId) ? show(grantId) : notASample()),
    moveTimeline: (grantId, move) => {
      const timeline = timelines.get(grantId);
      if (!timeline) return notASample();
      const { state } = timeline;
      const from = state.now;
      if (move.next_highlight) {
        // Ruling 77: to the next highlight H, skipping the human steps on the
        // way, except H's own, which are held for the user. It stops at the
        // later of H's event and the due times of H's own steps.
        const target = events.find((e) => !state.played.has(e.id) && e.highlight);
        if (!target) return Promise.reject(new ApiError(409, "No highlight is left to play."));
        // Ruling 86: while a highlight's own step is due and unmade, it waits for the user.
        const waiting = ownStepWaiting(events, state, stepHighlights);
        if (waiting) return Promise.reject(new ApiError(409, waiting));
        // The highlights' own steps still to come. A sign-off never moves the stop: it's
        // held, and Closeout stops on its own event.
        const own = scriptedSteps(events).filter(
          (step) =>
            !!stepHighlights[step.id] &&
            step.decision?.data.kind !== "sign_off" &&
            !isDone(step, state) &&
            time(step.at) > time(state.now),
        );
        const earlier = own.filter((step) => stepHighlights[step.id] !== target.highlight && time(step.at) <= time(target.at));
        if (earlier.length > 0) {
          // An earlier highlight's own step comes due first: the move stops there and holds it.
          playTo(events, state, earlier[0].at);
        } else {
          const ownDue = own.filter((step) => stepHighlights[step.id] === target.highlight).map((step) => step.at);
          const stop = [target.at, ...ownDue].reduce((a, b) => (time(b) > time(a) ? b : a));
          playTo(events, state, stop);
          // Ruling 85: Now names the highlight the move reached, even where it stopped later.
          state.stoppedOn = target.id;
        }
        skipHumanSteps(events, state, stepHighlights, from, target.highlight);
        return show(grantId);
      }
      const to = move.to ?? events.find((e) => !state.played.has(e.id))?.at;
      if (!to) return Promise.reject(new ApiError(409, "Nothing is left to play."));
      if (time(to) < time(state.now)) return Promise.reject(new ApiError(409, "The timeline only moves forward."));
      playTo(events, state, to);
      if (move.skip_human_steps) skipHumanSteps(events, state, stepHighlights, from);
      return show(grantId);
    },
    startOver: (grantId, confirmed) => {
      if (confirmed !== true) return Promise.reject(new ApiError(422, "Starting over needs the user's confirmation."));
      const timeline = timelines.get(grantId);
      if (!timeline) return notASample();
      timeline.state = startState(events);
      return show(grantId);
    },
    deliverForMe: (grantId, eventId) => {
      const timeline = timelines.get(grantId);
      if (!timeline) return notASample();
      const event = events.find((e) => e.id === eventId);
      if (!event || event.kind !== "user_delivery" || !timeline.state.played.has(eventId)) return served<TimelineView>(undefined);
      if (!timeline.state.delivered.has(eventId)) {
        // The user's own delivery shows under Just happened too (ruling 44), untagged.
        timeline.state.delivered.set(eventId, timeline.state.now);
        if (!timeline.state.justHappened.includes(eventId)) timeline.state.justHappened.push(eventId);
      }
      return show(grantId);
    },
    deliveryFileUrl: (grantId, eventId) => {
      const event = events.find((e) => e.id === eventId);
      const file = event?.file_id ? sample.files.find((f) => f.id === event.file_id) : undefined;
      const text = file ? SAMPLE_DOCUMENTS[file.name] : undefined;
      if (!timelines.has(grantId) || !file || text === undefined) return served<FileLink>(undefined);
      return served<FileLink>({ url: dataUrl(text, file.media_type), media_type: file.media_type, expires_at: "2099-01-01T00:00:00Z" });
    },
  };
}
