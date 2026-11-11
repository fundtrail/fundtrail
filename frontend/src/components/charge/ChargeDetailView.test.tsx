import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { sampleChargeDetails } from "@/lib/api/fixtures/charge";
import { sampleThreads } from "@/lib/api/fixtures/thread";
import { RecordThreadView } from "../thread/RecordThreadView";
import { ChargeDetailView } from "./ChargeDetailView";

const noop = vi.fn(async () => {});

describe("ChargeDetailView on the sample grant", () => {
  it("renders L-1002 with its bucket, the server's reason, its checklist, bill, answer, history and thread", () => {
    const detail = sampleChargeDetails()["chg-l-1002"];
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} />);

    expect(screen.getByRole("heading", { level: 1, name: "Sediment DNA sequencing run 7" })).toBeInTheDocument();
    const reasons = screen.getByRole("list", { name: "Reasons" });
    expect(within(reasons).getByText("Cost date Feb 20, 2026 is after the grant's end date, Jan 31, 2026.")).toBeInTheDocument();
    expect(within(reasons).getByText("Possible conflict")).toBeInTheDocument();

    const checklist = screen.getByRole("list", { name: "Evidence checklist" });
    expect(within(checklist).getByText("The facility's usage statement")).toBeInTheDocument();
    expect(within(checklist).getByText("Filled")).toBeInTheDocument();

    const bills = screen.getByRole("list", { name: "Bills and evidence covering this charge" });
    expect(within(bills).getByText("$2,180.00 of $2,180.00")).toBeInTheDocument();

    const answer = screen.getByTestId("answer");
    expect(within(answer).getByText("Supports")).toBeInTheDocument();
    expect(within(answer).getByText(/The agent's answer/)).toBeInTheDocument();

    const history = screen.getByRole("list", { name: "Status history" });
    expect(within(history).getByText(/ledger line L-1002 arrived/)).toBeInTheDocument();

    const thread = screen.getByRole("list", { name: "Review thread" });
    expect(within(thread).getByText("Is there anything on file that extends the grant past January 31?")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask the agent about L-1002")).toBeInTheDocument();
  });
});

describe("RecordThreadView on the sample grant", () => {
  it("shows the waiting extension term's thread with Accept and Reject", () => {
    const thread = sampleThreads().records["rec-period-extension"];
    const record = thread.entries[0].kind === "record" ? thread.entries[0].record : null;
    render(
      <RecordThreadView recordId="rec-period-extension" record={record} state="waiting" status={null} files={{}} thread={thread} onDecide={noop} onAsk={noop} />,
    );
    const box = screen.getByTestId("suggestion");
    expect(within(box).getByText("Ends Jan 31, 2027")).toBeInTheDocument();
    expect(within(box).getByRole("button", { name: /Accept/ })).toBeInTheDocument();
    expect(within(box).getByRole("button", { name: /Reject/ })).toBeInTheDocument();
  });
});

describe("the title's heading level", () => {
  it("is an h1 on the charge's own page, and an h2 when another page asks", () => {
    const detail = sampleChargeDetails()["chg-l-1002"];
    const { unmount } = render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} />);
    expect(screen.getByRole("heading", { level: 1, name: "Sediment DNA sequencing run 7" })).toBeInTheDocument();
    unmount();
    render(<ChargeDetailView detail={detail} onDecide={noop} onAsk={noop} headingLevel={2} />);
    expect(screen.getByRole("heading", { level: 2, name: "Sediment DNA sequencing run 7" })).toBeInTheDocument();
    expect(screen.queryAllByRole("heading", { level: 1 })).toHaveLength(0);
  });

  it("is an h1 on the record's own page, and an h2 when another page asks", () => {
    const thread = sampleThreads().records["rec-period-extension"];
    const record = thread.entries[0].kind === "record" ? thread.entries[0].record : null;
    const props = { recordId: "rec-period-extension", record, state: "waiting" as const, status: null, files: {}, thread, onDecide: noop, onAsk: noop };
    const { unmount } = render(<RecordThreadView {...props} />);
    expect(screen.getByRole("heading", { level: 1, name: "Period of performance" })).toBeInTheDocument();
    unmount();
    render(<RecordThreadView {...props} headingLevel={2} />);
    expect(screen.getByRole("heading", { level: 2, name: "Period of performance" })).toBeInTheDocument();
    expect(screen.queryAllByRole("heading", { level: 1 })).toHaveLength(0);
  });
});
