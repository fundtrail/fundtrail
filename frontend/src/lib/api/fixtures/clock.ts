// The workspace clock and resetting the workspace. Owned by the clock screen's
// builder.
//
// The fake starts at FAKE_NOW. The sample has nothing left to arrive after it
// (the next step is the accountant confirming the extension), so the fake
// holds one synthetic arrival for the clock controls to show: a receipt photo
// uploaded on Apr 12, 2026. Reaching it moves only the clock; no other fixture
// changes, since the fake has no agent and no checks. After it, nothing waits.
//
// Moving the clock only moves forward; an earlier time is a 422, as the server
// answers.

import { ApiError, type ApiClient } from "../client";
import type { Clock, NextArrival, Workspace } from "../types";
import { FAKE_NOW, sampleWorkspace, served, WORKSPACE_ID } from "./sample";

/** What waits for the fake clock, in arrival order. Synthetic. */
export const FAKE_ARRIVALS: NextArrival[] = [{ at: "2026-04-12T15:00:00Z", source: "upload", name: "receipt_boat_rental.jpg" }];

const t = (iso: string) => new Date(iso).getTime();

/** The clock at `now`, with the first arrival still ahead of it. */
export function clockAt(now: string): Clock {
  const next = FAKE_ARRIVALS.find((a) => t(a.at) > t(now)) ?? null;
  return { now, simulated: true, next_arrival_at: next?.at ?? null, next_arrival: next };
}

export const SAMPLE_CLOCK: Clock = clockAt(FAKE_NOW);

export function clockFake(): Pick<ApiClient, "getClock" | "moveClock" | "resetWorkspace"> {
  let clock = structuredClone(SAMPLE_CLOCK);
  return {
    getClock: (workspaceId) => served(workspaceId === WORKSPACE_ID ? clock : undefined),
    moveClock: (workspaceId, move) => {
      if (workspaceId !== WORKSPACE_ID) return served<Clock>(undefined);
      const to = move.to ?? clock.next_arrival_at;
      if (!to) return Promise.reject(new ApiError(422, "Nothing is waiting for the clock."));
      if (t(to) < t(clock.now)) {
        return Promise.reject(new ApiError(422, "The clock only moves forward."));
      }
      clock = clockAt(to);
      return served(clock);
    },
    resetWorkspace: (workspaceId) => {
      if (workspaceId !== WORKSPACE_ID) return served<Workspace>(undefined);
      clock = structuredClone(SAMPLE_CLOCK);
      return served(sampleWorkspace);
    },
  };
}
