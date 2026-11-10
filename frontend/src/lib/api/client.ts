import type {
  AgentRun,
  ChargeDetail,
  ChargeRow,
  Clock,
  ClockMove,
  EvidenceCard,
  EvidenceFile,
  FileLink,
  FtRecord,
  Grant,
  GrantDetail,
  GrantSummary,
  HeldMail,
  Id,
  LedgerUploadResult,
  NewRecordInput,
  ProblemList,
  RecordView,
  Thread,
  ThreadMessage,
  Workspace,
} from "./types";

/**
 * What the screens read from and send to the server: one method per endpoint
 * in contracts.md section 12 that the screens use, plus the thread routes and
 * the problem list. The HTTP client and the fake both implement it.
 */
export interface ApiClient {
  // Workspaces and the clock
  listWorkspaces(): Promise<Workspace[]>;
  createWorkspace(name: string): Promise<Workspace>;
  resetWorkspace(workspaceId: Id): Promise<Workspace>;
  getClock(workspaceId: Id): Promise<Clock>;
  /** No `to` moves to the next arrival. The clock only moves forward. */
  moveClock(workspaceId: Id, move: ClockMove): Promise<Clock>;

  // Grants
  listGrants(workspaceId: Id): Promise<GrantSummary[]>;
  /** Adding a grant: the award letter. The grant comes back at once; its terms follow. */
  createGrant(workspaceId: Id, awardLetter: Blob, fileName: string): Promise<Grant>;
  getGrant(grantId: Id): Promise<GrantDetail>;
  getProblemList(grantId: Id): Promise<ProblemList>;
  listCharges(grantId: Id): Promise<ChargeRow[]>;
  uploadLedger(grantId: Id, ledger: Blob, fileName: string): Promise<LedgerUploadResult>;
  listEvidence(grantId: Id): Promise<EvidenceCard[]>;
  uploadEvidence(grantId: Id, file: Blob, fileName: string): Promise<EvidenceFile>;
  listRecords(grantId: Id): Promise<RecordView[]>;
  /** Every accountant decision. A write the write check rejects is an ApiError with status 422. */
  writeRecord(grantId: Id, body: NewRecordInput): Promise<FtRecord>;
  listRuns(grantId: Id): Promise<AgentRun[]>;
  /** The evidence report's current draft, a PDF. */
  getReport(grantId: Id): Promise<Blob>;

  // A charge, a file, threads
  getCharge(chargeId: Id): Promise<ChargeDetail>;
  getFileLink(fileId: Id): Promise<FileLink>;
  getChargeThread(chargeId: Id): Promise<Thread>;
  getRecordThread(recordId: Id): Promise<Thread>;
  postChargeMessage(chargeId: Id, text: string): Promise<ThreadMessage>;
  postRecordMessage(recordId: Id, text: string): Promise<ThreadMessage>;

  /**
   * A workspace's held mail (decision 0025). No workspace route exists yet, so
   * this gathers the held-mail rows from each grant's problem list.
   */
  listHeldMail(workspaceId: Id): Promise<HeldMail[]>;
}

/** An error from the API, with FastAPI's `detail` when it sent one. A 422 from the write check carries its problems. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : `Request failed with status ${status}`);
    this.name = "ApiError";
  }

  /** The write check's problems, when this is its 422. */
  get problems(): string[] | null {
    return this.status === 422 && Array.isArray(this.detail) && this.detail.every((d) => typeof d === "string")
      ? (this.detail as string[])
      : null;
  }
}

const e = encodeURIComponent;

/**
 * The real client. Every request carries the Supabase access token as
 * `Authorization: Bearer <token>` (contracts.md section 12); without a token
 * nothing is sent.
 */
export class HttpApiClient implements ApiClient {
  constructor(
    private readonly baseUrl: string,
    private readonly getAccessToken: () => Promise<string | null>,
  ) {}

  private async send(path: string, init: { method?: string; body?: BodyInit; json?: unknown; accept?: string } = {}): Promise<Response> {
    const token = await this.getAccessToken();
    if (!token) throw new ApiError(401, "Not signed in");
    const headers: Record<string, string> = { Accept: init.accept ?? "application/json", Authorization: `Bearer ${token}` };
    let body = init.body;
    if (init.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(init.json);
    }
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      headers,
      ...(init.method ? { method: init.method } : {}),
      ...(body !== undefined ? { body } : {}),
    });
    if (!response.ok) {
      let detail: unknown = null;
      try {
        detail = ((await response.json()) as { detail?: unknown }).detail ?? null;
      } catch {
        // The body wasn't JSON. The status says enough.
      }
      throw new ApiError(response.status, detail);
    }
    return response;
  }

  private async get<T>(path: string): Promise<T> {
    return (await (await this.send(path)).json()) as T;
  }

  private async post<T>(path: string, json?: unknown): Promise<T> {
    return (await (await this.send(path, { method: "POST", json })).json()) as T;
  }

  private async postFile<T>(path: string, file: Blob, fileName: string): Promise<T> {
    const form = new FormData();
    form.append("file", file, fileName);
    return (await (await this.send(path, { method: "POST", body: form })).json()) as T;
  }

  listWorkspaces() {
    return this.get<Workspace[]>("/workspaces");
  }
  createWorkspace(name: string) {
    return this.post<Workspace>("/workspaces", { name });
  }
  resetWorkspace(workspaceId: Id) {
    return this.post<Workspace>(`/workspaces/${e(workspaceId)}/reset`);
  }
  getClock(workspaceId: Id) {
    return this.get<Clock>(`/workspaces/${e(workspaceId)}/clock`);
  }
  moveClock(workspaceId: Id, move: ClockMove) {
    return this.post<Clock>(`/workspaces/${e(workspaceId)}/clock`, move);
  }
  listGrants(workspaceId: Id) {
    return this.get<GrantSummary[]>(`/workspaces/${e(workspaceId)}/grants`);
  }
  createGrant(workspaceId: Id, awardLetter: Blob, fileName: string) {
    return this.postFile<Grant>(`/workspaces/${e(workspaceId)}/grants`, awardLetter, fileName);
  }
  getGrant(grantId: Id) {
    return this.get<GrantDetail>(`/grants/${e(grantId)}`);
  }
  getProblemList(grantId: Id) {
    return this.get<ProblemList>(`/grants/${e(grantId)}/problems`);
  }
  listCharges(grantId: Id) {
    return this.get<ChargeRow[]>(`/grants/${e(grantId)}/charges`);
  }
  uploadLedger(grantId: Id, ledger: Blob, fileName: string) {
    return this.postFile<LedgerUploadResult>(`/grants/${e(grantId)}/ledger`, ledger, fileName);
  }
  listEvidence(grantId: Id) {
    return this.get<EvidenceCard[]>(`/grants/${e(grantId)}/evidence`);
  }
  uploadEvidence(grantId: Id, file: Blob, fileName: string) {
    return this.postFile<EvidenceFile>(`/grants/${e(grantId)}/evidence`, file, fileName);
  }
  listRecords(grantId: Id) {
    return this.get<RecordView[]>(`/grants/${e(grantId)}/records`);
  }
  writeRecord(grantId: Id, body: NewRecordInput) {
    return this.post<FtRecord>(`/grants/${e(grantId)}/records`, body);
  }
  listRuns(grantId: Id) {
    return this.get<AgentRun[]>(`/grants/${e(grantId)}/runs`);
  }
  async getReport(grantId: Id) {
    return (await this.send(`/grants/${e(grantId)}/report`, { accept: "application/pdf" })).blob();
  }
  getCharge(chargeId: Id) {
    return this.get<ChargeDetail>(`/charges/${e(chargeId)}`);
  }
  getFileLink(fileId: Id) {
    return this.get<FileLink>(`/evidence/${e(fileId)}/content`);
  }
  getChargeThread(chargeId: Id) {
    return this.get<Thread>(`/charges/${e(chargeId)}/thread`);
  }
  getRecordThread(recordId: Id) {
    return this.get<Thread>(`/records/${e(recordId)}/thread`);
  }
  postChargeMessage(chargeId: Id, text: string) {
    return this.post<ThreadMessage>(`/charges/${e(chargeId)}/thread`, { text });
  }
  postRecordMessage(recordId: Id, text: string) {
    return this.post<ThreadMessage>(`/records/${e(recordId)}/thread`, { text });
  }
  async listHeldMail(workspaceId: Id) {
    const grants = await this.listGrants(workspaceId);
    const lists = await Promise.all(grants.map((g) => this.getProblemList(g.grant.id)));
    return lists.flatMap((list) => list.rows.flatMap((row) => (row.kind === "held_mail" ? [row.held] : [])));
  }
}
