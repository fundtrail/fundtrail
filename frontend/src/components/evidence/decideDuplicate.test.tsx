import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiProvider, type ApiClient, type EvidenceCard, type FtRecord } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { DUPLICATE_MARK } from "@/lib/api/fixtures/duplicate";
import { FakeAuthProvider } from "@/lib/auth";
import { EvidenceCardView } from "./EvidenceCardView";

// Issue 353: the agent's duplicate mark, waiting, is decided on the copy's card.

const GRANT = "grant-sample";
const COPY = "sequencing_statement_forwarded.eml";

async function cards(): Promise<EvidenceCard[]> {
  return createFakeApiClient().listEvidence(GRANT);
}

async function card(name: string): Promise<EvidenceCard> {
  const found = (await cards()).find((c) => c.file.name === name);
  if (!found) throw new Error(`no card ${name}`);
  return found;
}

function withApi(client: Partial<ApiClient>, children: ReactNode) {
  return (
    <FakeAuthProvider>
      <ApiProvider client={client as ApiClient}>{children}</ApiProvider>
    </FakeAuthProvider>
  );
}

/** A write that stays in flight until the test settles it. */
function deferredWrite() {
  const settle: { resolve: (r: FtRecord) => void; reject: (e: unknown) => void }[] = [];
  const writeRecord = vi.fn<ApiClient["writeRecord"]>(
    () =>
      new Promise<FtRecord>((resolve, reject) => {
        settle.push({ resolve, reject });
      }),
  );
  return { writeRecord, settle };
}

const decision = () => screen.getByRole("group", { name: "The agent's duplicate mark" });

describe("the agent's duplicate mark on the copy's card", () => {
  it("offers Confirm and Reject while the server says the mark waits", async () => {
    const copy = await card(COPY);
    expect(copy.duplicate?.state).toBe("waiting");
    render(withApi({}, <EvidenceCardView grantId={GRANT} card={copy} />));
    expect(screen.getByText("Copy of sequencing_statement.eml · Waiting for the accountant")).toBeInTheDocument();
    const group = decision();
    for (const name of ["Confirm", "Reject"]) {
      const button = within(group).getByRole("button", { name });
      expect(button).toBeEnabled();
      expect(button.className).not.toContain("ft-btn--main");
    }
    expect(within(group).getByRole("button", { name: "Confirm" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--approve");
    expect(within(group).getByRole("button", { name: "Reject" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--reject");
  });

  for (const [name, value] of [
    ["Confirm", "confirmed"],
    ["Reject", "rejected"],
  ] as const) {
    it(`${name} sends one confirmation naming the mark, even on a double submit`, async () => {
      const { writeRecord, settle } = deferredWrite();
      render(withApi({ writeRecord }, <EvidenceCardView grantId={GRANT} card={await card(COPY)} />));
      const button = within(decision()).getByRole("button", { name });
      act(() => {
        button.click();
        button.click();
      });
      expect(writeRecord).toHaveBeenCalledTimes(1);
      expect(writeRecord.mock.calls[0][0]).toBe(GRANT);
      expect(writeRecord.mock.calls[0][1]).toStrictEqual({
        data: { kind: "confirmation", record_ids: [DUPLICATE_MARK.id], decision: value },
      });
      expect(within(decision()).getByRole("button", { name: "Confirm" })).toBeDisabled();
      expect(within(decision()).getByRole("button", { name: "Reject" })).toBeDisabled();
      await act(async () => settle[0].resolve({ ...DUPLICATE_MARK, id: "rec-new", author: "user" } as unknown as FtRecord));
      // Nothing of its own after the write: the refetch shows the server's state.
      expect(screen.queryByText(/^Confirmed|^Rejected/)).toBeNull();
      fireEvent.click(within(decision()).getByRole("button", { name }));
      expect(writeRecord).toHaveBeenCalledTimes(1);
    });
  }

  it("shows the server's words when it refuses, and lets the accountant try again", async () => {
    const writeRecord = vi.fn<ApiClient["writeRecord"]>(async () => {
      throw new ApiError(422, ["The duplicate mark isn't waiting for the accountant."]);
    });
    render(withApi({ writeRecord }, <EvidenceCardView grantId={GRANT} card={await card(COPY)} />));
    fireEvent.click(within(decision()).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The duplicate mark isn't waiting for the accountant.");
    expect(within(decision()).getByRole("button", { name: "Confirm" })).toBeEnabled();
  });

  it("offers nothing once the mark counts, or on a file with no mark", async () => {
    const copy = await card(COPY);
    const counted: EvidenceCard = { ...copy, duplicate: { ...copy.duplicate!, state: "counts" } };
    const { unmount } = render(withApi({}, <EvidenceCardView grantId={GRANT} card={counted} />));
    expect(screen.getByText("Copy of sequencing_statement.eml")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "The agent's duplicate mark" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
    unmount();
    render(withApi({}, <EvidenceCardView grantId={GRANT} card={await card("invoice_1001.txt")} />));
    expect(screen.queryByRole("group", { name: "The agent's duplicate mark" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Reject" })).toBeNull();
  });

  it("in fake mode, a confirmation clears the mark from the card and the charge", async () => {
    for (const [value, after] of [
      ["confirmed", "counts"],
      ["rejected", null],
    ] as const) {
      const api = createFakeApiClient();
      const before = await api.getCharge("chg-l-1002");
      expect(before.waiting?.map((w) => w.record.id)).toEqual([DUPLICATE_MARK.id]);
      expect(before.status?.reasons.some((r) => r.check === "suggestion" && r.record_ids?.includes(DUPLICATE_MARK.id))).toBe(true);
      expect(before.status?.bucket).toBe("possible_conflict");

      await api.writeRecord(GRANT, { data: { kind: "confirmation", record_ids: [DUPLICATE_MARK.id], decision: value } });

      const copy = (await api.listEvidence(GRANT)).find((c) => c.file.name === COPY);
      expect(copy?.duplicate?.state ?? null).toBe(after);
      const charge = await api.getCharge("chg-l-1002");
      expect(charge.waiting).toEqual([]);
      expect(charge.status?.reasons.some((r) => r.check === "suggestion")).toBe(false);
      // Each client keeps its own: a fresh one still has the mark waiting.
      expect((await createFakeApiClient().getCharge("chg-l-1002")).waiting).toHaveLength(1);
    }
  });

  it("refreshes the card from the fake after Confirm, so it shows the server's state", async () => {
    const api = createFakeApiClient();
    function Card() {
      return <EvidenceCardView grantId={GRANT} card={shown} />;
    }
    let shown = (await api.listEvidence(GRANT)).find((c) => c.file.name === COPY)!;
    const { rerender } = render(withApi(api, <Card />));
    fireEvent.click(within(decision()).getByRole("button", { name: "Confirm" }));
    await waitFor(async () => expect((await api.listEvidence(GRANT)).find((c) => c.file.name === COPY)?.duplicate?.state).toBe("counts"));
    shown = (await api.listEvidence(GRANT)).find((c) => c.file.name === COPY)!;
    rerender(withApi(api, <Card />));
    expect(screen.getByText("Copy of sequencing_statement.eml")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "The agent's duplicate mark" })).toBeNull();
  });
});
