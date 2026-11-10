import type {
  ChargeRow,
  Clock,
  GrantDetail,
  GrantSummary,
  Id,
  ProblemList,
  Workspace,
} from "./types";

/** What the screens read from the server. The HTTP client and the fake both implement it. */
export interface ApiClient {
  listWorkspaces(): Promise<Workspace[]>;
  getClock(workspaceId: Id): Promise<Clock>;
  listGrants(workspaceId: Id): Promise<GrantSummary[]>;
  getGrant(grantId: Id): Promise<GrantDetail>;
  getProblemList(grantId: Id): Promise<ProblemList>;
  listCharges(grantId: Id): Promise<ChargeRow[]>;
}

/** An error from the API, with FastAPI's `detail` when it sent one. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `Request failed with status ${status}`);
    this.name = "ApiError";
  }
}

/**
 * The real client. Every request carries the Supabase access token as
 * `Authorization: Bearer <token>` (contracts.md section 12).
 */
export class HttpApiClient implements ApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly getAccessToken: () => Promise<string | null>,
  ) {}

  private async get<T>(path: string): Promise<T> {
    const token = await this.getAccessToken();
    // Every request carries the token. Without one, nothing is sent.
    if (!token) throw new ApiError(401, "Not signed in");
    const headers = { Accept: "application/json", Authorization: `Bearer ${token}` };
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, { headers });
    if (!response.ok) {
      let detail: unknown = null;
      try {
        detail = ((await response.json()) as { detail?: unknown }).detail ?? null;
      } catch {
        // The body wasn't JSON. The status says enough.
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as T;
  }

  listWorkspaces() {
    return this.get<Workspace[]>("/workspaces");
  }
  getClock(workspaceId: Id) {
    return this.get<Clock>(`/workspaces/${encodeURIComponent(workspaceId)}/clock`);
  }
  listGrants(workspaceId: Id) {
    return this.get<GrantSummary[]>(`/workspaces/${encodeURIComponent(workspaceId)}/grants`);
  }
  getGrant(grantId: Id) {
    return this.get<GrantDetail>(`/grants/${encodeURIComponent(grantId)}`);
  }
  getProblemList(grantId: Id) {
    return this.get<ProblemList>(`/grants/${encodeURIComponent(grantId)}/problems`);
  }
  listCharges(grantId: Id) {
    return this.get<ChargeRow[]>(`/grants/${encodeURIComponent(grantId)}/charges`);
  }
}
