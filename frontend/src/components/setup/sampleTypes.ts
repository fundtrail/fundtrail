// Stand-ins for the sample grant bodies settled for issue #165 (SampleChoice,
// SampleOption, SampleCreate in backend/app/contracts/). Temporary: once the
// contracts PR lands and lib/api types them, this file goes and the imports
// point at "@/lib/api" instead, with the same names.

import type { Id } from "@/lib/api";

export type SampleChoice = "small_live" | "larger_live" | "larger_prerun";

/** One option of GET /samples, in dropdown order. Names and descriptions come from the sample packs. */
export interface SampleOption {
  choice: SampleChoice;
  name: string;
  description: string;
  /** True for the larger sample read live: it asks for a confirm step before it starts. */
  needs_confirm: boolean;
  available: boolean;
  unavailable_reason?: string | null;
}

/** POST /workspaces/{workspace_id}/samples */
export interface SampleCreate {
  choice: SampleChoice;
  confirmed?: boolean;
}

/** The grant a 409 names when the one-at-a-time rule refuses a sample. */
export interface BlockingGrant {
  id: Id;
  name: string;
}
