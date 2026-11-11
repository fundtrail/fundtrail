// What went wrong with a request, in words a screen can show. Behavior only:
// how a message looks is each screen's.

import { ApiError } from "./client";

export type ErrorKind = "session" | "not_found" | "server" | "connection" | "rejected" | "other";

export interface DescribedError {
  kind: ErrorKind;
  message: string;
}

/** A request's error as a kind and a short message (placeholder wording). */
export function describeError(error: unknown): DescribedError {
  if (error instanceof ApiError) {
    if (error.status === 401) return { kind: "session", message: "Your session has expired. Sign in again." };
    if (error.status === 403 || error.status === 404) return { kind: "not_found", message: "Not found, or not yours to see." };
    if (error.status >= 500) return { kind: "server", message: "The server had a problem. Try again in a moment." };
    const problems = error.problems;
    if (problems && problems.length > 0) return { kind: "rejected", message: problems.join(" ") };
    if (typeof error.detail === "string" && error.detail) return { kind: "rejected", message: error.detail };
    return { kind: "other", message: `Something went wrong (status ${error.status}).` };
  }
  // Anything that isn't the server's answer means no answer came: fetch throws
  // its own error (a TypeError) when the network fails.
  return { kind: "connection", message: "Couldn't reach the server. Check your connection and try again." };
}
