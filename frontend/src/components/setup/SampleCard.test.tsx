import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError, type GrantSummary } from "@/lib/api";
import { readBlockingGrant, SampleCard } from "./SampleCard";
import type { SampleOption } from "./sampleTypes";

// Placeholder options in GET /samples' order. Names and descriptions are made up.
const OPTIONS: SampleOption[] = [
  { choice: "small_live", name: "Small sample", description: "A small grant read live.", needs_confirm: false, available: true },
  { choice: "larger_live", name: "Larger sample, read live", description: "A larger grant read live from the start.", needs_confirm: true, available: true },
  {
    choice: "larger_prerun",
    name: "Larger sample, already read",
    description: "A larger grant the agent has already read.",
    needs_confirm: false,
    available: false,
    unavailable_reason: "Being prepared again.",
  },
];

function summary(id: string): GrantSummary {
  return { grant: { id } } as GrantSummary;
}

function setup(openSample = vi.fn(async () => summary("grant-new"))) {
  const onOpened = vi.fn();
  render(<SampleCard options={OPTIONS} openSample={openSample} onOpened={onOpened} />);
  const choose = (value: string) => fireEvent.change(screen.getByLabelText("Which sample"), { target: { value } });
  return { openSample, onOpened, choose };
}

describe("SampleCard", () => {
  it("starts with nothing chosen and says to choose one on Open", () => {
    const { openSample } = setup();
    expect(screen.getByLabelText("Which sample")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a sample first.");
    expect(openSample).not.toHaveBeenCalled();
  });

  it("changes the description with the choice and opens a sample that needs no confirm", async () => {
    const { openSample, onOpened, choose } = setup();
    choose("small_live");
    expect(screen.getByText("A small grant read live.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() => expect(onOpened).toHaveBeenCalledWith("grant-new"));
    expect(openSample).toHaveBeenCalledWith({ choice: "small_live", confirmed: false });
  });

  it("asks for a confirm step before the larger live sample starts", async () => {
    const { openSample, onOpened, choose } = setup();
    choose("larger_live");
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(openSample).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Start it" }));
    await waitFor(() => expect(onOpened).toHaveBeenCalled());
    expect(openSample).toHaveBeenCalledWith({ choice: "larger_live", confirmed: true });
  });

  it("shows an unavailable option's reason and doesn't open it", () => {
    const { choose } = setup();
    choose("larger_prerun");
    expect(screen.getByText("Being prepared again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open" })).toBeDisabled();
  });

  it("names the grant that blocks a sample, with a link", async () => {
    const refuse = vi.fn(async () => {
      throw new ApiError(409, { grant: { id: "grant-running", workspace_id: "ws", funder: "NSF", award_number: "SYN-1", title: "Running sample" } });
    });
    const { choose } = setup(refuse);
    choose("larger_live");
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    fireEvent.click(screen.getByRole("button", { name: "Start it" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Another sample is still running:");
    expect(screen.getByRole("link", { name: "Running sample" })).toHaveAttribute("href", "/grants/grant-running");
  });
});

describe("readBlockingGrant", () => {
  it("reads a grant or a grant summary, and nothing else", () => {
    expect(readBlockingGrant({ grant: { id: "g", title: null, award_number: "SYN-2" } })).toEqual({ id: "g", name: "SYN-2" });
    expect(readBlockingGrant({ grant: { grant: { id: "g", title: "T" } } })).toEqual({ id: "g", name: "T" });
    expect(readBlockingGrant("Confirm first")).toBeNull();
  });
});
