// The workspace clock and resetting the workspace. Owned by the clock screen's
// builder.
//
// The fake starts at FAKE_NOW. Nothing in the sample arrives after it (the
// next step is the accountant confirming the extension), so there's no next
// arrival. Moving the clock only moves forward; an earlier time is a 422, as
// the server answers.

import { ApiError, type ApiClient } from "../client";
import type { Clock, Workspace } from "../types";
import { FAKE_NOW, sampleWorkspace, served, WORKSPACE_ID } from "./sample";

export const SAMPLE_CLOCK: Clock = { now: FAKE_NOW, simulated: true, next_arrival_at: null, next_arrival: null };

export function clockFake(): Pick<ApiClient, "getClock" | "moveClock" | "resetWorkspace"> {
  let clock = structuredClone(SAMPLE_CLOCK);
  return {
    getClock: (workspaceId) => served(workspaceId === WORKSPACE_ID ? clock : undefined),
    moveClock: (workspaceId, move) => {
      if (workspaceId !== WORKSPACE_ID) return served<Clock>(undefined);
      const to = move.to ?? clock.next_arrival_at;
      if (!to) return Promise.reject(new ApiError(422, "Nothing is waiting for the clock."));
      if (new Date(to).getTime() < new Date(clock.now).getTime()) {
        return Promise.reject(new ApiError(422, "The clock only moves forward."));
      }
      clock = { ...clock, now: to };
      return served(clock);
    },
    resetWorkspace: (workspaceId) => {
      if (workspaceId !== WORKSPACE_ID) return served<Workspace>(undefined);
      clock = structuredClone(SAMPLE_CLOCK);
      return served(sampleWorkspace);
    },
  };
}
