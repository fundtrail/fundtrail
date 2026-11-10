import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SAMPLE_HELD_MAIL } from "@/lib/api/fixtures/sample";
import { fakeHarness } from "../setup/testing";
import { HeldMailList } from "./HeldMailList";

describe("HeldMailList", () => {
  it("shows each held message with why it's held and its files", async () => {
    const { client, Wrapper } = fakeHarness();
    const mail = await client.listHeldMail("ws-sample");
    render(<HeldMailList mail={mail} />, { wrapper: Wrapper });
    const message = screen.getByRole("listitem", { name: "Held message Invoice INV-1001" });
    expect(within(message).getByText("The sender isn't a known sender.")).toBeInTheDocument();
    expect(within(message).getByText(/billing@labsupply\.example/)).toBeInTheDocument();
    expect(within(within(message).getByRole("list", { name: "Files" })).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "message.eml",
      "INV-1001.pdf",
    ]);
    expect(within(message).queryByRole("list", { name: "Skipped files" })).not.toBeInTheDocument();
  });

  it("letting mail in writes a mail action on its grant", async () => {
    const { writeRecord, Wrapper } = fakeHarness();
    render(<HeldMailList mail={SAMPLE_HELD_MAIL} />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Let in" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Let in."));
    expect(writeRecord).toHaveBeenCalledWith("grant-sample", {
      data: { kind: "mail_action", held_mail_id: "held-inv-1001-copy", action: "let_in" },
    });
  });

  it("dismissing writes a dismissal", async () => {
    const { writeRecord, Wrapper } = fakeHarness();
    render(<HeldMailList mail={SAMPLE_HELD_MAIL} />, { wrapper: Wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(writeRecord).toHaveBeenCalled());
    expect(writeRecord.mock.calls[0]![1]).toEqual({
      data: { kind: "mail_action", held_mail_id: "held-inv-1001-copy", action: "dismiss" },
    });
  });

  it("shows a message's skipped files when the server sends them", () => {
    const { Wrapper } = fakeHarness();
    const held = {
      ...SAMPLE_HELD_MAIL[0]!,
      skipped: [
        {
          workspace_id: "ws-sample",
          grant_id: "grant-sample",
          name: "scan.tiff",
          source: "gmail" as const,
          source_ref: "gmail-synthetic-0002",
          reason: "too_large" as const,
          skipped_at: "2026-04-08T14:10:00Z",
        },
      ],
    };
    render(<HeldMailList mail={[held]} />, { wrapper: Wrapper });
    expect(within(screen.getByRole("list", { name: "Skipped files" })).getByText("scan.tiff")).toBeInTheDocument();
  });

  it("says so when no mail is held", () => {
    render(<HeldMailList mail={[]} />);
    expect(screen.getByText("No mail is held.")).toBeInTheDocument();
  });
});
