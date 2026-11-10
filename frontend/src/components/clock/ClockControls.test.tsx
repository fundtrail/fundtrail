import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, ApiProvider, type ApiClient, type Clock } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { WORKSPACE_ID } from "@/lib/api/fixtures/sample";
import { StaticAuthProvider, type Auth } from "@/lib/auth";
import { ClockControls, ClockPanel } from "./ClockControls";

const auth: Auth = {
  state: { status: "signed_in", user: { id: "user-1", email: "accountant@university.example", name: null } },
  fake: true,
  signIn: async () => {},
  signOut: async () => {},
  getAccessToken: async () => null,
};

function wrap(client: ApiClient, children: ReactNode) {
  return (
    <StaticAuthProvider value={auth}>
      <ApiProvider client={client}>{children}</ApiProvider>
    </StaticAuthProvider>
  );
}

const demoClock: Clock = {
  now: "2026-04-09T18:00:00Z",
  simulated: true,
  next_arrival_at: "2026-04-12T15:00:00Z",
  next_arrival: { at: "2026-04-12T15:00:00Z", source: "upload", name: "receipt.jpg" },
};

function panel(clock: Clock, moveClock = vi.fn(async () => clock)) {
  const client = { moveClock } as unknown as ApiClient;
  render(wrap(client, <ClockPanel workspaceId="ws" clock={clock} onMoved={() => {}} />));
  return moveClock;
}

describe("ClockControls", () => {
  it("shows the next arrival in the demo workspace", () => {
    panel(demoClock);
    expect(screen.getByTestId("next-arrival")).toHaveTextContent("Next arrival: Apr 12, 2026, receipt.jpg (upload)");
  });

  it("has no controls on a real clock", () => {
    panel({ now: "2026-11-10T12:00:00Z", simulated: false });
    expect(screen.getByTestId("clock-now")).toHaveTextContent("Nov 10, 2026");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Go forward to")).not.toBeInTheDocument();
  });

  it("goes to the next arrival with an empty move", async () => {
    const move = panel(demoClock);
    fireEvent.click(screen.getByRole("button", { name: "Go to next arrival" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith("ws", {}));
  });

  it("never offers a date at or before now", () => {
    const move = panel(demoClock);
    const field = screen.getByLabelText("Go forward to");
    expect(field).toHaveAttribute("min", "2026-04-10");

    for (const earlier of ["2026-04-09", "2026-01-01"]) {
      fireEvent.change(field, { target: { value: earlier } });
      expect(screen.getByRole("button", { name: "Go" })).toBeDisabled();
      expect(screen.getByRole("status")).toHaveTextContent("The clock only moves forward.");
      fireEvent.submit(field.closest("form")!);
    }
    expect(move).not.toHaveBeenCalled();
  });

  it("moves forward to a chosen date", async () => {
    const move = panel(demoClock);
    fireEvent.change(screen.getByLabelText("Go forward to"), { target: { value: "2026-05-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    await waitFor(() => expect(move).toHaveBeenCalledWith("ws", { to: "2026-05-01T00:00:00Z" }));
  });

  it("shows the server's refusal as it comes", async () => {
    panel(demoClock, vi.fn(async () => Promise.reject(new ApiError(422, "The clock only moves forward."))));
    fireEvent.click(screen.getByRole("button", { name: "Go to next arrival" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The clock only moves forward.");
  });

  it("moves the fake clock forward to its next arrival, and then nothing waits", async () => {
    render(wrap(createFakeApiClient(), <ClockControls workspaceId={WORKSPACE_ID} />));
    const button = await screen.findByRole("button", { name: "Go to next arrival" });
    expect(screen.getByTestId("clock-now")).toHaveTextContent("Apr 9, 2026");
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByTestId("clock-now")).toHaveTextContent("Apr 12, 2026"));
    expect(screen.getByTestId("next-arrival")).toHaveTextContent("Nothing is waiting for the clock.");
    expect(screen.getByRole("button", { name: "Go to next arrival" })).toBeDisabled();
  });
});
