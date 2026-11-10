import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiProvider, type ApiClient, type FtRecord, type SignOff, type SignOffState } from "@/lib/api";
import { StaticAuthProvider, type Auth } from "@/lib/auth";
import { SignOffPanel } from "./SignOffPanel";

const auth: Auth = {
  state: { status: "signed_in", user: { id: "user-1", email: "accountant@university.example", name: null } },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

const signedRecord: FtRecord<SignOff> = {
  id: "rec-sign-off",
  workspace_id: "ws",
  grant_id: "g-1",
  author: "user",
  author_user_id: "user-1",
  written_at: "2026-04-12T10:00:00Z",
  data: {
    kind: "sign_off",
    note: "L-1002 waits on the extension.",
    report_path: "ws/g-1/reports/r.pdf",
    report_sha256: "abc123",
    snapshot: {
      charges: [],
      problem_rows: [],
      totals: {
        ledger_total_cents: 0,
        charges_total: 0,
        charges_ready: 0,
        accepted: 0,
        reversed: 0,
        bucket_counts: { evidence_complete: 0, possible_conflict: 0, missing_evidence: 0, needs_human: 0 },
      },
    },
  },
};

function setup(writeRecord: ApiClient["writeRecord"], signOff: SignOffState = { state: "not_signed", sign_off: null, changes: [] }) {
  const onSigned = vi.fn();
  render(
    <StaticAuthProvider value={auth}>
      <ApiProvider client={{ writeRecord } as unknown as ApiClient}>
        <SignOffPanel grantId="g-1" signOff={signOff} onSigned={onSigned} />
      </ApiProvider>
    </StaticAuthProvider>,
  );
  return onSigned;
}

describe("SignOffPanel", () => {
  it("shows the server's refusal when a note is required, and puts the cursor in the note", async () => {
    const write = vi.fn(async () =>
      Promise.reject(new ApiError(422, ["A note is required: 3 charges aren't ready for closeout."])),
    );
    const onSigned = setup(write);
    fireEvent.click(screen.getByRole("button", { name: "Sign off" }));

    await waitFor(() => expect(write).toHaveBeenCalledWith("g-1", { data: { kind: "sign_off", note: null } }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A note is required: 3 charges aren't ready for closeout.");
    expect(screen.getByLabelText("Note")).toHaveFocus();
    expect(screen.getByLabelText("Note")).toHaveAttribute("aria-invalid", "true");
    expect(onSigned).not.toHaveBeenCalled();
  });

  it("sends the note as written and shows the sign-off the server stored", async () => {
    const write = vi.fn(async () => signedRecord as FtRecord);
    const onSigned = setup(write);
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "  L-1002 waits on the extension.  " } });
    fireEvent.click(screen.getByRole("button", { name: "Sign off" }));

    await waitFor(() =>
      expect(write).toHaveBeenCalledWith("g-1", { data: { kind: "sign_off", note: "L-1002 waits on the extension." } }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Signed off Apr 12, 2026.");
    expect(onSigned).toHaveBeenCalledWith(signedRecord);
  });

  it("never decides on its own: a sign-off with no note goes to the server", async () => {
    const write = vi.fn(async () => signedRecord as FtRecord);
    setup(write);
    expect(screen.getByRole("button", { name: "Sign off" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "Sign off" }));
    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
  });

  it("shows a refusal that comes as a sentence, such as a run in progress", async () => {
    setup(vi.fn(async () => Promise.reject(new ApiError(409, "The agent is still working on this grant. Try again when it's done."))));
    fireEvent.click(screen.getByRole("button", { name: "Sign off" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The agent is still working on this grant.");
  });

  it("shows what changed since sign-off and offers to sign off again", () => {
    setup(vi.fn(), {
      state: "changed",
      sign_off: signedRecord,
      changes: [{ kind: "charge", subject: "chg-l-1002", before: "possible_conflict", after: "evidence_complete" }],
    });
    expect(screen.getByTestId("sign-off-state")).toHaveTextContent("Changed since sign-off.");
    expect(screen.getByTestId("sign-off-state")).toHaveTextContent("L-1002 waits on the extension.");
    expect(screen.getByRole("table", { name: "What changed since sign-off" })).toHaveTextContent("chg-l-1002");
    expect(screen.getByRole("button", { name: "Sign off again" })).toBeInTheDocument();
  });
});

describe("withdrawing a sign-off", () => {
  const signedState: SignOffState = { state: "signed", sign_off: signedRecord, changes: [] };

  it("isn't offered before anything is signed", () => {
    setup(vi.fn());
    expect(screen.queryByRole("button", { name: "Withdraw the sign-off" })).not.toBeInTheDocument();
  });

  it("writes a retraction that replaces the current sign-off", async () => {
    const retraction: FtRecord = {
      ...signedRecord,
      id: "rec-retraction",
      written_at: "2026-04-13T09:00:00Z",
      replaces_id: signedRecord.id,
      data: { kind: "retraction", reason: "A bill arrived late." },
    };
    const write = vi.fn(async () => retraction);
    const onChanged = setup(write, signedState);
    fireEvent.change(screen.getByLabelText("Reason for withdrawing"), { target: { value: " A bill arrived late. " } });
    fireEvent.click(screen.getByRole("button", { name: "Withdraw the sign-off" }));

    await waitFor(() =>
      expect(write).toHaveBeenCalledWith("g-1", {
        data: { kind: "retraction", reason: "A bill arrived late." },
        replaces_id: "rec-sign-off",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Sign-off withdrawn Apr 13, 2026.");
    expect(onChanged).toHaveBeenCalledWith(retraction);
  });

  it("sends no reason when none is given, and shows the server's refusal", async () => {
    const write = vi.fn(async () => Promise.reject(new ApiError(422, ["Only the accountant can withdraw a sign-off."])));
    setup(write, signedState);
    fireEvent.click(screen.getByRole("button", { name: "Withdraw the sign-off" }));
    await waitFor(() =>
      expect(write).toHaveBeenCalledWith("g-1", { data: { kind: "retraction", reason: null }, replaces_id: "rec-sign-off" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the accountant can withdraw a sign-off.");
  });
});
