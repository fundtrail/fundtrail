import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Bucket, ChargeStatus } from "@/lib/api";
import { BucketBadge, ChargeStatusBadge } from "./BucketBadge";

const cases: [Bucket, string, string][] = [
  ["possible_conflict", "Possible conflict", "ft-badge--conflict"],
  ["needs_human", "Needs a human", "ft-badge--human"],
  ["missing_evidence", "Missing evidence", "ft-badge--missing"],
  ["evidence_complete", "Evidence complete", "ft-badge--complete"],
];

function status(bucket: Bucket, flags: Partial<ChargeStatus> = {}): ChargeStatus {
  return {
    grant_id: "g",
    charge_id: "c",
    bucket,
    reasons: [],
    checklist: [],
    flagged: false,
    rechecking: false,
    accepted: false,
    snoozed: false,
    ...flags,
  };
}

describe("BucketBadge", () => {
  it.each(cases)("shows %s as its exact name with its own style", (bucket, label, className) => {
    render(<BucketBadge bucket={bucket} />);
    const badge = screen.getByText(label);
    expect(badge).toHaveClass("ft-badge", className);
    expect(badge).toHaveAttribute("data-bucket", bucket);
  });

  it("always shows the word, so a bucket is never a color or a mark alone", () => {
    for (const [bucket, label] of cases) {
      const { unmount } = render(<BucketBadge bucket={bucket} />);
      expect(screen.getByText(label).textContent).toBe(label);
      unmount();
    }
  });
});

describe("ChargeStatusBadge", () => {
  it("says the charge isn't checked yet when it has no status", () => {
    render(<ChargeStatusBadge status={null} />);
    expect(screen.getByText("Not checked yet")).toBeInTheDocument();
    expect(document.querySelector(".ft-badge")).toBeNull();
  });

  it("keeps the bucket and adds Rechecking while the agent answers again", () => {
    render(<ChargeStatusBadge status={status("needs_human", { rechecking: true })} />);
    expect(screen.getByText("Needs a human")).toBeInTheDocument();
    expect(screen.getByText("Rechecking")).toBeInTheDocument();
  });

  it("shows Accepted with the bucket the checks gave underneath, never as Evidence complete", () => {
    render(<ChargeStatusBadge status={status("missing_evidence", { accepted: true })} />);
    const accepted = screen.getByText("Accepted");
    const bucket = screen.getByText("Missing evidence");
    // Accepted comes first, the bucket underneath.
    expect(accepted.compareDocumentPosition(bucket) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText("Evidence complete")).toBeNull();
  });

  it("shows Snoozed beside the bucket", () => {
    render(<ChargeStatusBadge status={status("possible_conflict", { snoozed: true })} />);
    expect(screen.getByText("Possible conflict")).toBeInTheDocument();
    expect(screen.getByText("Snoozed")).toBeInTheDocument();
  });
});
