import type {
  AgentRun,
  ChargeDetail,
  ChargeRow,
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
  SampleCreate,
  SampleOption,
  SampleRefusal,
  TimelineMove,
  TimelineView,
} from "./types";

/**
 * What the screens read from and send to the server: one method per endpoint
 * in contracts.md section 12 that the screens use, plus the thread routes and
 * the problem list. The HTTP client and the fake both implement it.
 */
export interface ApiClient {
  // Workspaces
  listWorkspaces(): Promise<Workspace[]>;
  createWorkspace(name: string): Promise<Workspace>;
  resetWorkspace(workspaceId: Id): Promise<Workspace>;

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

  // Sample grants (ruling 40). Every timeline method is a 404 on a grant that isn't a sample.
  /** The Sample dropdown's choices, in order. */
  listSamples(): Promise<SampleOption[]>;
  /** Opens a sample grant. A refusal (409) throws SampleRefusalError. */
  createSample(workspaceId: Id, body: SampleCreate): Promise<GrantSummary>;
  getTimeline(grantId: Id): Promise<TimelineView>;
  /**
   * No `to` plays to the next event. Forward only: earlier is a 409. A move
   * refused while another larger read-live sample is still working throws
   * SampleRefusalError.
   */
  moveTimeline(grantId: Id, move: TimelineMove): Promise<TimelineView>;
  /**
   * Starts the one grant over. `confirmed` must be true: only call it after the
   * user has confirmed in the panel's confirm step. A refusal (409) throws
   * SampleRefusalError.
   */
  startOver(grantId: Id, confirmed: true): Promise<TimelineView>;
  /** "Deliver for me": brings in an item the user was to deliver. */
  deliverForMe(grantId: Id, eventId: Id): Promise<TimelineView>;
  /** "Get the file": a short-lived link to an item the user was to deliver. */
  deliveryFileUrl(grantId: Id, eventId: Id): Promise<FileLink>;
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

/** A 409 refusing to open a sample or move its clock, with the server's reason (ruling 41). */
export class SampleRefusalError extends ApiError {
  constructor(readonly refusal: SampleRefusal) {
    super(409, refusal);
    this.name = "SampleRefusalError";
    this.message = refusal.message;
  }
}

function isSampleRefusal(detail: unknown): detail is SampleRefusal {
  return typeof detail === "object" && detail !== null && "reason" in detail && "message" in detail;
}

/** Turns a 409 carrying a SampleRefusal into a SampleRefusalError. */
async function refusable<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (error) {
    if (error instanceof ApiError && error.status === 409 && isSampleRefusal(error.detail)) throw new SampleRefusalError(error.detail);
    throw error;
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
    /** Called when the session is gone or refused (401), before the error is thrown. */
    private readonly onUnauthorized?: () => void,
  ) {}

  private async send(path: string, init: { method?: string; body?: BodyInit; json?: unknown; accept?: string } = {}): Promise<Response> {
    const token = await this.getAccessToken();
    if (!token) {
      this.onUnauthorized?.();
      throw new ApiError(401, "Not signed in");
    }
    const headers: Record<string, string> = { Accept: init.accept ?? "application/json", Authorization: `Bearer ${token}` };
    let body = init.body;
    if (init.json !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(init.json);
    }
    // A network failure throws fetch's own error (a TypeError), not an ApiError:
    // callers tell a connection problem from a server's answer that way.
    const response = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
      headers,
      ...(init.method ? { method: init.method } : {}),
      ...(body !== undefined ? { body } : {}),
    });
    if (response.status === 401) this.onUnauthorized?.();
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
  listSamples() {
    return this.get<SampleOption[]>("/samples");
  }
  createSample(workspaceId: Id, body: SampleCreate) {
    return refusable(this.post<GrantSummary>(`/workspaces/${e(workspaceId)}/samples`, body));
  }
  getTimeline(grantId: Id) {
    return this.get<TimelineView>(`/grants/${e(grantId)}/timeline`);
  }
  moveTimeline(grantId: Id, move: TimelineMove) {
    return refusable(this.post<TimelineView>(`/grants/${e(grantId)}/timeline`, move));
  }
  startOver(grantId: Id, confirmed: true) {
    return refusable(this.post<TimelineView>(`/grants/${e(grantId)}/timeline/start-over`, { confirmed }));
  }
  deliverForMe(grantId: Id, eventId: Id) {
    return this.post<TimelineView>(`/grants/${e(grantId)}/timeline/deliveries/${e(eventId)}`);
  }
  deliveryFileUrl(grantId: Id, eventId: Id) {
    return this.get<FileLink>(`/grants/${e(grantId)}/timeline/deliveries/${e(eventId)}/file`);
  }
}
