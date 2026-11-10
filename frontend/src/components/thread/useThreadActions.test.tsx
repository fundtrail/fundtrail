import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, useCharge, type ApiClient, type ChargeDetail } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { StaticAuthProvider, type Auth } from "@/lib/auth";
import { useThreadActions } from "./useThreadActions";

const auth: Auth = {
  state: { status: "signed_in", user: { id: "user-1", email: "accountant@university.example", name: null } },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

type Actions = ReturnType<typeof useThreadActions>;

function Probe({ onActions }: { onActions: (a: Actions) => void }) {
  const data = useCharge("charge-1");
  onActions(useThreadActions("grant-1", { chargeId: "charge-1" }));
  return <p data-testid="loads">{data.data ? data.data.charge.id : "none"}</p>;
}

function setup() {
  const client = createFakeApiClient();
  const writeRecord = vi.fn(async () => ({}) as Awaited<ReturnType<ApiClient["writeRecord"]>>);
  const postChargeMessage = vi.fn(async () => ({}) as Awaited<ReturnType<ApiClient["postChargeMessage"]>>);
  // Counts the screen's loads of the charge, so a test sees the refetch after a write.
  const load = vi.fn(async () => ({ charge: { id: "charge-1" } }) as ChargeDetail);
  const api: ApiClient = { ...client, writeRecord, postChargeMessage, getCharge: load };
  let actions: Actions | undefined;
  render(
    <StaticAuthProvider value={auth}>
      <ApiProvider client={api}>
        <Probe onActions={(a) => (actions = a)} />
      </ApiProvider>
    </StaticAuthProvider>,
  );
  return { writeRecord, postChargeMessage, load, actions: () => actions! };
}

describe("useThreadActions", () => {
  it("posts Accept as a confirmation record and refetches the screen", async () => {
    const { writeRecord, load, actions } = setup();
    await waitFor(() => expect(screen.getByTestId("loads")).toHaveTextContent("charge-1"));
    await act(() => actions().decide("rec-dispute", "confirmed"));
    expect(writeRecord).toHaveBeenCalledWith("grant-1", {
      data: { kind: "confirmation", record_ids: ["rec-dispute"], decision: "confirmed" },
    });
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it("posts Reject as a rejected confirmation", async () => {
    const { writeRecord, actions } = setup();
    await act(() => actions().decide("rec-suggestion", "rejected"));
    expect(writeRecord).toHaveBeenCalledWith("grant-1", {
      data: { kind: "confirmation", record_ids: ["rec-suggestion"], decision: "rejected" },
    });
  });

  it("posts a question to the charge's thread and refetches", async () => {
    const { postChargeMessage, load, actions } = setup();
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    await act(() => actions().ask("Is there a quote?"));
    expect(postChargeMessage).toHaveBeenCalledWith("charge-1", "Is there a quote?");
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });

  it("sends any of the accountant's records as it is, and refetches", async () => {
    const { writeRecord, load, actions } = setup();
    await waitFor(() => expect(load).toHaveBeenCalledTimes(1));
    const input = { data: { kind: "snooze" as const, charge_id: "charge-1", until: "2026-05-01", note: "Refund coming.", reasons: [{ check: "checklist", problem: "missing_item" }] } };
    await act(() => actions().write(input));
    expect(writeRecord).toHaveBeenCalledWith("grant-1", input);
    await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  });
});
