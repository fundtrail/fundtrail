import { ApiError, type ApiClient } from "./client";
import { chargeLists, clocks, grantDetails, grantSummaries, problemLists, workspaces } from "./fixtures";
import type { Id } from "./types";

function found<T>(value: T | undefined): Promise<T> {
  // A copy, so a screen can never change the fixture under another screen.
  return value === undefined
    ? Promise.reject(new ApiError(404, "Not Found"))
    : Promise.resolve(structuredClone(value));
}

/** The API served from synthetic fixtures, for development and tests. */
export class FakeApiClient implements ApiClient {
  listWorkspaces() {
    return found(workspaces);
  }
  getClock(workspaceId: Id) {
    return found(clocks[workspaceId]);
  }
  listGrants(workspaceId: Id) {
    return found(grantSummaries[workspaceId]);
  }
  getGrant(grantId: Id) {
    return found(grantDetails[grantId]);
  }
  getProblemList(grantId: Id) {
    return found(problemLists[grantId]);
  }
  listCharges(grantId: Id) {
    return found(chargeLists[grantId]);
  }
}
