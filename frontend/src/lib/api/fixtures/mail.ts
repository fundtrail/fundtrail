// Mail held for the sample grant (decision 0025). Owned by the mail screen's
// builder. The held message itself is SAMPLE_HELD_MAIL in sample.ts, shared
// with the grant's problem list.

import type { ApiClient } from "../client";
import { SAMPLE_HELD_MAIL, served, WORKSPACE_ID } from "./sample";

export function mailFake(): Pick<ApiClient, "listHeldMail"> {
  return { listHeldMail: (workspaceId) => served(workspaceId === WORKSPACE_ID ? SAMPLE_HELD_MAIL : undefined) };
}
