import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

/** The page's main buttons: pull request 265 fills ft-btn--main, so there is at most one at a time. */
function mainButtons() {
  return document.querySelectorAll(".ft-btn--main");
}

describe("why sign-off is unavailable (ruling 72)", () => {
  const reason = "The agent is still working on this grant. Sign off once it's done.";

  it("shows the server's reason under Sign off, tied to the button, and sends nothing", () => {
    const write = vi.fn();
    setup(write, { state: "not_signed", sign_off: null, changes: [], unavailable_reason: reason });
    const button = screen.getByRole("button", { name: "Sign off" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAccessibleDescription(reason);
    expect(screen.getByText(reason)).toBeInTheDocument();
    fireEvent.click(button);
    expect(write).not.toHaveBeenCalled();
  });

  it("sends nothing with a reason present, by click, by Enter in the note, or by submitting the form", () => {
    const write = vi.fn();
    setup(write, { state: "not_signed", sign_off: null, changes: [], unavailable_reason: reason });
    const note = screen.getByLabelText("Note");
    fireEvent.change(note, { target: { value: "L-1002 waits on the extension." } });
    fireEvent.click(screen.getByRole("button", { name: "Sign off" }));
    fireEvent.keyDown(note, { key: "Enter", code: "Enter" });
    // Enter in a textarea adds a line; the form's own submit covers any other way of sending it.
    fireEvent.submit(screen.getByRole("form", { name: "Sign off" }));
    expect(write).not.toHaveBeenCalled();
  });

  it.each([
    ["null", { unavailable_reason: null }],
    ["absent", {}],
  ])("leaves Sign off working when the reason is %s, and sends the request", async (_, extra) => {
    const write = vi.fn(async () => signedRecord as FtRecord);
    setup(write, { state: "not_signed", sign_off: null, changes: [], ...extra });
    const button = screen.getByRole("button", { name: "Sign off" });
    expect(button).not.toHaveAttribute("aria-disabled");
    expect(button).not.toHaveAttribute("aria-describedby");
    expect(button).toHaveAccessibleDescription("");
    // No reason line of any wording renders without the server's field.
    expect(document.querySelector(".ft-co-unavailable")).toBeNull();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.click(button);
    await waitFor(() => expect(write).toHaveBeenCalledWith("g-1", { data: { kind: "sign_off", note: null } }));
    expect(write).toHaveBeenCalledTimes(1);
  });

  it("is a polite live region that announces again on a press, and not on a refetch", () => {
    vi.useFakeTimers();
    try {
      const signOff: SignOffState = { state: "not_signed", sign_off: null, changes: [], unavailable_reason: reason };
      const view = (state: SignOffState) => (
        <StaticAuthProvider value={auth}>
          <ApiProvider client={{ writeRecord: vi.fn() } as unknown as ApiClient}>
            <SignOffPanel grantId="g-1" signOff={state} onSigned={vi.fn()} />
          </ApiProvider>
        </StaticAuthProvider>
      );
      const { rerender } = render(view(signOff));
      const status = screen.getByRole("status");
      expect(status).toHaveTextContent(reason);
      expect(status).toHaveAttribute("id", screen.getByRole("button", { name: "Sign off" }).getAttribute("aria-describedby"));

      // A refetch with the same reason leaves the text untouched, so nothing is announced.
      const text = status.firstChild;
      rerender(view({ ...signOff }));
      expect(screen.getByRole("status").firstChild).toBe(text);

      // A press withdraws the text from screen readers for a moment, then brings it back.
      fireEvent.click(screen.getByRole("button", { name: "Sign off" }));
      expect(status.querySelector('[aria-hidden="true"]')).toHaveTextContent(reason);
      act(() => vi.advanceTimersByTime(150));
      expect(status.querySelector('[aria-hidden="true"]')).toBeNull();
      expect(status).toHaveTextContent(reason);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("why signing again is unavailable (ruling 79)", () => {
  const reason = "The agent is still working on this grant. Sign off once it's done.";
  const signedState: SignOffState = { state: "signed", sign_off: signedRecord, changes: [] };

  it("shows the server's reason next to Sign off again, which then opens nothing and sends nothing", () => {
    const write = vi.fn();
    setup(write, { ...signedState, unavailable_reason: reason });
    const again = screen.getByRole("button", { name: "Sign off again" });
    expect(again).toHaveAttribute("aria-disabled", "true");
    expect(again).toHaveAccessibleDescription(reason);
    expect(screen.getByRole("status")).toHaveTextContent(reason);
    fireEvent.click(again);
    expect(screen.queryByLabelText("Note")).not.toBeInTheDocument();
    expect(write).not.toHaveBeenCalled();
  });

  it("opens the form as today when the server gives no reason", () => {
    setup(vi.fn(), { ...signedState, unavailable_reason: null });
    const again = screen.getByRole("button", { name: "Sign off again" });
    expect(again).not.toHaveAttribute("aria-disabled");
    expect(again).toHaveAccessibleDescription("");
    expect(document.querySelector(".ft-co-unavailable")).toBeNull();
    fireEvent.click(again);
    expect(screen.getByLabelText("Note")).toHaveFocus();
  });
});

describe("once signed, signing again is quiet", () => {
  const signedState: SignOffState = { state: "signed", sign_off: signedRecord, changes: [] };

  it("has one main button before signing, and keeps it when the server refuses", async () => {
    setup(vi.fn(async () => Promise.reject(new ApiError(422, ["A note is required: 3 charges aren't ready for closeout."]))));
    expect(mainButtons()).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Sign off" }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(mainButtons()).toHaveLength(1);
  });

  it("leads with the stored sign-off and offers Sign off again as a quiet button, with no main button", () => {
    setup(vi.fn(), signedState);
    expect(screen.getByTestId("sign-off-state")).toHaveTextContent("Signed off.");
    expect(screen.queryByLabelText("Note")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign off again" })).not.toHaveClass("ft-btn--main");
    expect(mainButtons()).toHaveLength(0);
  });

  it("opens the same form in place, whose submit is then the one main button, and sends the same request", async () => {
    const write = vi.fn(async () => signedRecord as FtRecord);
    setup(write, signedState);
    fireEvent.click(screen.getByRole("button", { name: "Sign off again" }));
    expect(screen.getByLabelText("Note")).toHaveFocus();
    expect(mainButtons()).toHaveLength(1);
    const submit = screen.getByRole("button", { name: "Sign off again" });
    expect(submit).toHaveClass("ft-btn--main");
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: " Signed again after the extension. " } });
    fireEvent.click(submit);
    await waitFor(() =>
      expect(write).toHaveBeenCalledWith("g-1", { data: { kind: "sign_off", note: "Signed again after the extension." } }),
    );
  });

  it("keeps Sign off again quiet when the server says something changed", () => {
    setup(vi.fn(), {
      state: "changed",
      sign_off: signedRecord,
      changes: [{ kind: "charge", subject: "chg-l-1002", before: "possible_conflict", after: "evidence_complete" }],
    });
    expect(mainButtons()).toHaveLength(0);
  });

  it("closes the opened form with Cancel, sending nothing, and puts focus back on Sign off again", () => {
    const write = vi.fn();
    setup(write, { state: "signed", sign_off: signedRecord, changes: [] });
    fireEvent.click(screen.getByRole("button", { name: "Sign off again" }));
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Draft, not sent." } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByLabelText("Note")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign off again" })).toHaveFocus();
    expect(mainButtons()).toHaveLength(0);
    expect(write).not.toHaveBeenCalled();
    // The stored sign-off is untouched.
    expect(screen.getByTestId("sign-off-state")).toHaveTextContent("L-1002 waits on the extension.");
  });

  it("offers no Cancel before anything is signed", () => {
    setup(vi.fn());
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
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
