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
}

function emptyState(at: IsoDatetime): TimelineState {
  return { now: at, played: new Set(), delivered: new Map(), justHappened: [], stoppedOn: null, scripted: new Map(), byAccountant: new Set() };
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
  const last = past.filter((e) => e.kind !== "user_delivery").at(-1);
  state.justHappened = last ? [last.id] : [];
  state.stoppedOn = last?.id ?? null;
  return state;
}

function view(events: TimelineEvent[], state: TimelineState, problemRows: number): TimelineView {
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

/**
 * Skipping the human steps: as the clock passes them, the sample accountant
 * delivers what was the user's to deliver. Each item it delivered is listed
 * under Just happened, marked delivered_by_sample_accountant.
 *
 * Ruling 55: each of the sample's own accountant decisions is listed once,
 * under the latest event this move played or delivered at or before the
 * decision's time (an arrival, this move's own delivery, or a checks date),
 * or else under the move's first event. Never under a delivery from an
 * earlier move. A move that played and delivered nothing lists a decision
 * under the latest arrival before it.
 *
 * The fake only lists those decisions; it doesn't carry them out. It has no
 * checks, so the grant's terms, problem list and records stay as they are.
 */
function skipHumanSteps(events: TimelineEvent[], state: TimelineState, from: IsoDatetime) {
  for (const e of events) {
    if (e.kind === "user_delivery" && state.played.has(e.id) && !state.delivered.has(e.id)) {
      state.delivered.set(e.id, e.at);
      state.byAccountant.add(e.id);
      if (!state.justHappened.includes(e.id)) state.justHappened.push(e.id);
    }
  }
  // This move's events, in date order: what it played and what it delivered.
  const thisMove = events.filter((e) => state.justHappened.includes(e.id));
  const decisions = sample.records.filter((r) => r.author === "user" && time(r.written_at) > time(from) && time(r.written_at) <= time(state.now));
  for (const decision of decisions) {
    const before = (e: TimelineEvent) => time(e.at) <= time(decision.written_at);
    let on: TimelineEvent | undefined = thisMove.filter(before).at(-1) ?? thisMove[0];
    if (!on) {
      // Nothing happened in this move: the latest arrival before it, never an earlier move's delivery.
      on = events.filter((e) => e.kind !== "user_delivery" && state.played.has(e.id) && before(e)).at(-1);
      if (!on) continue;
      state.justHappened.push(on.id);
    }
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
}): Pick<ApiClient, "listSamples" | "createSample" | "getTimeline" | "moveTimeline" | "startOver" | "deliverForMe" | "deliveryFileUrl"> {
  const events = sampleEvents();
  const timelines = new Map<Id, { state: TimelineState }>([[SAMPLE_GRANT_ID, { state: sampleGrantState(events) }]]);
  const notASample = () => served<TimelineView>(undefined);
  const show = (grantId: Id) => served(view(events, timelines.get(grantId)!.state, grantId === SAMPLE_GRANT_ID ? hooks.problemRows : 0));

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
      const to = move.to ?? events.find((e) => !state.played.has(e.id))?.at;
      if (!to) return Promise.reject(new ApiError(409, "Nothing is coming up."));
      if (time(to) < time(state.now)) return Promise.reject(new ApiError(409, "The timeline only moves forward."));
      const from = state.now;
      playTo(events, state, to);
      if (move.skip_human_steps) skipHumanSteps(events, state, from);
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
