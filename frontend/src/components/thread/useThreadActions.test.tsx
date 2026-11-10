import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiProvider, type ApiClient } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { StaticAuthProvider, type Auth } from "@/lib/auth";
import { useServer, useThreadActions } from "./useThreadActions";

const auth: Auth = {
  state: { status: "signed_in", user: { id: "user-1", email: "accountant@university.example", name: null } },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

type Actions = ReturnType<typeof useThreadActions>;

function Probe({ load, onActions }: { load: () => Promise<number>; onActions: (a: Actions) => void }) {
  const data = useServer(["probe"], () => load());
  onActions(useThreadActions("grant-1", { chargeId: "charge-1" }));
  return <p data-testid="loads">{data.data ?? "none"}</p>;
}

function setup() {
  const client = createFakeApiClient();
  const writeRecord = vi.fn(async () => ({}) as Awaited<ReturnType<ApiClient["writeRecord"]>>);
  const postChargeMessage = vi.fn(async () => ({}) as Awaited<ReturnType<ApiClient["postChargeMessage"]>>);
  const api: ApiClient = { ...client, writeRecord, postChargeMessage };
  let loads = 0;
  const load = vi.fn(async () => ++loads);
  let actions: Actions | undefined;
  render(
    <StaticAuthProvider value={auth}>
      <ApiProvider client={api}>
        <Probe load={load} onActions={(a) => (actions = a)} />
      </ApiProvider>
    </StaticAuthProvider>,
  );
  return { writeRecord, postChargeMessage, load, actions: () => actions! };
}

describe("useThreadActions", () => {
  it("posts Accept as a confirmation record and refetches the screen", async () => {
    const { writeRecord, load, actions } = setup();
    await waitFor(() => expect(screen.getByTestId("loads")).toHaveTextContent("1"));
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
});
