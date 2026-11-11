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

  it("says the From line couldn't be read when a message has no sender", () => {
    const { Wrapper } = fakeHarness();
    for (const sender of [null, ""]) {
      const held = { ...SAMPLE_HELD_MAIL[0]!, id: `held-${String(sender)}`, sender, reason: "unverified_sender" as const };
      const { unmount } = render(<HeldMailList mail={[held]} />, { wrapper: Wrapper });
      expect(screen.getByText("The From line couldn't be read.")).toBeInTheDocument();
      expect(screen.queryByText(/couldn't be verified/)).not.toBeInTheDocument();
      unmount();
    }
  });

  it("shows when each message was held and which grant it is for", () => {
    const { Wrapper } = fakeHarness();
    render(<HeldMailList mail={SAMPLE_HELD_MAIL} grantNames={{ "grant-sample": "Sample grant name" }} />, { wrapper: Wrapper });
    const message = screen.getByRole("listitem", { name: "Held message Invoice INV-1001" });
    expect(within(message).getByText("Held Apr 8, 2026")).toBeInTheDocument();
    expect(within(message).getByText("Sample grant name")).toBeInTheDocument();
  });

  it("marks busy only the button that was pressed while its action saves", () => {
    for (const [pressed, other] of [
      ["Let in", "Dismiss"],
      ["Dismiss", "Let in"],
    ] as const) {
      const { writeRecord, Wrapper } = fakeHarness();
      writeRecord.mockReturnValue(new Promise(() => {}));
      const { unmount } = render(<HeldMailList mail={SAMPLE_HELD_MAIL} />, { wrapper: Wrapper });
      fireEvent.click(screen.getByRole("button", { name: pressed }));
      expect(screen.getByRole("button", { name: pressed })).toHaveClass("is-busy");
      expect(screen.getByRole("button", { name: other })).not.toHaveClass("is-busy");
      expect(screen.getByRole("button", { name: other })).toBeDisabled();
      unmount();
    }
  });

  describe("with several held messages", () => {
    const several = ["held-a", "held-b", "held-c"].map((id, i) => ({
      ...SAMPLE_HELD_MAIL[0]!,
      id,
      subject: `Invoice ${i + 1}`,
    }));

    it("fills no button: each row's Let in is an outlined approve, Dismiss its quiet partner", () => {
      const { Wrapper } = fakeHarness();
      const { container } = render(<HeldMailList mail={several} />, { wrapper: Wrapper });
      expect(container.querySelectorAll(".ft-btn--main")).toHaveLength(0);
      for (const n of [1, 2, 3]) {
        const row = screen.getByRole("listitem", { name: `Held message Invoice ${n}` });
        expect(within(row).getByRole("button", { name: "Let in" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--approve");
        expect(within(row).getByRole("button", { name: "Dismiss" })).toHaveClass("ft-btn", "ft-btn--sm", "ft-btn--quiet");
      }
    });

    it("sends each row's own action, as before", async () => {
      const { writeRecord, Wrapper } = fakeHarness();
      render(<HeldMailList mail={several} />, { wrapper: Wrapper });
      fireEvent.click(within(screen.getByRole("listitem", { name: "Held message Invoice 2" })).getByRole("button", { name: "Let in" }));
      await waitFor(() => expect(writeRecord).toHaveBeenCalledTimes(1));
      expect(writeRecord).toHaveBeenLastCalledWith("grant-sample", {
        data: { kind: "mail_action", held_mail_id: "held-b", action: "let_in" },
      });
      fireEvent.click(within(screen.getByRole("listitem", { name: "Held message Invoice 3" })).getByRole("button", { name: "Dismiss" }));
      await waitFor(() => expect(writeRecord).toHaveBeenCalledTimes(2));
      expect(writeRecord).toHaveBeenLastCalledWith("grant-sample", {
        data: { kind: "mail_action", held_mail_id: "held-c", action: "dismiss" },
      });
    });
  });

  it("says so when no mail is held", () => {
    render(<HeldMailList mail={[]} />);
    expect(screen.getByText("No mail is held.")).toBeInTheDocument();
  });
});
