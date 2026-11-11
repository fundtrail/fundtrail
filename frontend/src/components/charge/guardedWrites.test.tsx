import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiProvider, type ChargeStatus, type FtRecord, type GrantProblem, type NewRecordInput, type OpenQuestion, type Reason } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { GrantProblemPane } from "../GrantProblemPane";
import { AgentAnswers } from "./AgentAnswers";
import { EvidenceChecklist } from "./EvidenceChecklist";
import { StatusReasons } from "./StatusReasons";

// Two submits in the same task (requestSubmit() twice, say) both run before
// React re-renders the button disabled. These tests make both calls inside
// one act(), so neither sees the other's state, and keep the first write in
// flight while the second is made.

/** A write that stays in flight until the test settles it. */
function deferredWriter() {
  const settle: { resolve: () => void; reject: (e: unknown) => void }[] = [];
  const onWrite = vi.fn(
    (_input: NewRecordInput) =>
      new Promise<void>((resolve, reject) => {
        settle.push({ resolve, reject });
      }),
  );
  return { onWrite, settle };
}

function twice(fire: () => void) {
  act(() => {
    fire();
    fire();
  });
}

function record(id: string, author: "agent" | "user", data: Record<string, unknown>): FtRecord {
  return {
    id,
    workspace_id: "ws",
    grant_id: "g",
    author,
    author_user_id: author === "user" ? "u" : null,
    written_at: "2026-03-01T10:00:00Z",
    replaces_id: null,
    data: data as unknown as FtRecord["data"],
  } as FtRecord;
}

const reason: Reason = { check: "checklist", problem: "missing_item", text: "A bill isn't on file.", record_ids: ["r-item"], bucket: "missing_evidence" } as Reason;
const status = (r: Reason): ChargeStatus => ({ grant_id: "g", charge_id: "c", bucket: "missing_evidence", reasons: [r], checklist: [], flagged: true }) as ChargeStatus;

function openAccept() {
  fireEvent.click(screen.getByRole("button", { name: "Accept with a note" }));
  fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Refunded in March." } });
  return screen.getByRole("form", { name: /Accept with a note/ }) as HTMLFormElement;
}

describe("the charge's writes never send twice at once", () => {
  it("Accept with a note: two submits send one record, and the blocked one changes nothing", async () => {
    const { onWrite, settle } = deferredWriter();
    render(<StatusReasons status={status(reason)} onWrite={onWrite} />);
    const form = openAccept();
    twice(() => form.requestSubmit());
    expect(onWrite).toHaveBeenCalledTimes(1);
    // The blocked call left the first call's busy state and errors alone, and the form open.
    expect(within(form).getByRole("button", { name: "Accept" })).toBeDisabled();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("form", { name: /Accept with a note/ })).toBeInTheDocument();
    await act(async () => settle[0].resolve());
    await waitFor(() => expect(screen.queryByRole("form", { name: /Accept with a note/ })).toBeNull());
    expect(onWrite).toHaveBeenCalledTimes(1);
  });

  it("releases the guard after a refusal, so a retry sends", async () => {
    const { onWrite, settle } = deferredWriter();
    render(<StatusReasons status={status(reason)} onWrite={onWrite} />);
    const form = openAccept();
    twice(() => form.requestSubmit());
    expect(onWrite).toHaveBeenCalledTimes(1);
    await act(async () => settle[0].reject(new ApiError(422, ["The note is too short."])));
    expect(await screen.findByText("The note is too short.")).toBeInTheDocument();
    act(() => form.requestSubmit());
    expect(onWrite).toHaveBeenCalledTimes(2);
  });

  it("releases the guard after a synchronous throw, so a retry sends", async () => {
    const onWrite = vi.fn<(input: NewRecordInput) => Promise<void>>(() => {
      throw new Error("offline");
    });
    render(<StatusReasons status={status(reason)} onWrite={onWrite} />);
    const form = openAccept();
    act(() => form.requestSubmit());
    expect(await screen.findByText("Couldn't reach the server. Nothing was saved.")).toBeInTheDocument();
    act(() => form.requestSubmit());
    expect(onWrite).toHaveBeenCalledTimes(2);
  });

  it("Snooze: two submits send one record", () => {
    const { onWrite } = deferredWriter();
    render(<StatusReasons status={status(reason)} onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Snooze" }));
    fireEvent.change(screen.getByLabelText("Until"), { target: { value: "2026-05-01" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Refund coming." } });
    const form = screen.getByRole("form", { name: "Snooze this charge" }) as HTMLFormElement;
    twice(() => form.requestSubmit());
    expect(onWrite).toHaveBeenCalledTimes(1);
  });

  it("Save answer: two submits send one record", () => {
    const { onWrite } = deferredWriter();
    const question: OpenQuestion = { charge_id: "c", question: "covers", record_id: "r-approval", answer_by: "user" };
    render(<AgentAnswers answers={[]} questions={[question]} rechecking={false} files={{}} chargeId="c" onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Answer" }));
    fireEvent.click(screen.getByLabelText("Supports"));
    fireEvent.change(screen.getByLabelText("Your reasoning"), { target: { value: "Approved in Research.gov." } });
    const form = screen.getByRole("form", { name: "Answer" }) as HTMLFormElement;
    twice(() => form.requestSubmit());
    expect(onWrite).toHaveBeenCalledTimes(1);
  });

  it("Add item: two submits send one record", () => {
    const { onWrite } = deferredWriter();
    render(<EvidenceChecklist checklist={[]} links={[]} waiting={[]} records={{}} files={{}} chargeId="c" onWrite={onWrite} />);
    fireEvent.click(screen.getByRole("button", { name: "Add item" }));
    fireEvent.change(screen.getByLabelText("What's needed"), { target: { value: "Airfare receipt" } });
    const form = screen.getByRole("form", { name: "Add a checklist item" }) as HTMLFormElement;
    twice(() => form.requestSubmit());
    expect(onWrite).toHaveBeenCalledTimes(1);
  });

  it("Reopen: two clicks send one retraction", () => {
    const { onWrite } = deferredWriter();
    const accepted = record("r-acc", "user", { kind: "accepted_reason", charge_id: "c", note: "Refunded.", reusable: false });
    render(<StatusReasons status={status({ ...reason, accepted_by: "r-acc" })} records={{ [accepted.id]: accepted }} onWrite={onWrite} />);
    const reopen = screen.getByRole("button", { name: "Reopen" });
    twice(() => reopen.click());
    expect(onWrite).toHaveBeenCalledTimes(1);
  });

  it("the offered note: two clicks send one acceptance", () => {
    const { onWrite } = deferredWriter();
    const note = record("r-note", "user", { kind: "accepted_reason", charge_id: "c-april", note: "Facility fee, no invoice.", reusable: true });
    render(<StatusReasons status={status({ ...reason, offered_note_id: "r-note" })} records={{ [note.id]: note }} onWrite={onWrite} />);
    const button = within(screen.getByTestId("offered-note")).getByRole("button", { name: "Just this charge" });
    twice(() => button.click());
    expect(onWrite).toHaveBeenCalledTimes(1);
  });
});

describe("the grant problem pane's Accept", () => {
  it("sends one record for two submits", async () => {
    const client = createFakeApiClient();
    const writeRecord = vi.fn(() => new Promise<FtRecord>(() => {}));
    client.writeRecord = writeRecord;
    const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };
    function Wrapper({ children }: { children: ReactNode }) {
      return (
        <StaticAuthProvider value={auth}>
          <ApiProvider client={client}>{children}</ApiProvider>
        </StaticAuthProvider>
      );
    }
    const problem = { check: "terms", problem: "conflicting_terms", text: "Two confirmed terms disagree.", record_ids: [], flagged: true } as unknown as GrantProblem;
    render(<GrantProblemPane grantId="grant-sample" problem={problem} />, { wrapper: Wrapper });
    const form = openAccept();
    twice(() => form.requestSubmit());
    expect(writeRecord).toHaveBeenCalledTimes(1);
  });
});
