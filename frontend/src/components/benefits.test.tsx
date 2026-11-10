import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BudgetLine, Charge, ChargeStatus, ChecklistEntry, FtRecord, Rate, Reason } from "@/lib/api";
import { sampleCharge, sampleRecord } from "@/lib/api/fixtures/sample";
import { EvidenceChecklist } from "./charge/EvidenceChecklist";
import { StatusReasons } from "./charge/StatusReasons";
import { ProblemList } from "./ProblemList";

const benefits: Charge = { ...sampleCharge("chg-l-1002"), id: "chg-benefits", ledger_line_id: "L-2002", description: "Benefits, March", amount_cents: 36_600 };
const salary: Charge = { ...sampleCharge("chg-l-1001"), id: "chg-salary", ledger_line_id: "L-2001", description: "Salary, March", amount_cents: 100_000 };

const mismatch: Reason = {
  check: "checklist",
  problem: "recalculation_mismatch",
  text: "Benefits don't match the rate times the salary lines.",
  record_ids: ["rec-rate"],
  bucket: "needs_human",
  expected_cents: 36_000,
};

function status(charge: Charge, reasons: Reason[], checklist: ChecklistEntry[] = []): ChargeStatus {
  return { grant_id: charge.grant_id, charge_id: charge.id, bucket: "needs_human", reasons, checklist, flagged: true };
}

const rate: FtRecord<Rate> = {
  ...sampleRecord<FtRecord<BudgetLine>>("rec-budget-other"),
  id: "rec-rate",
  data: {
    kind: "rate",
    dated: { value: "2025-07-01" },
    name: { value: "Staff benefits" },
    rate: { value: "0.366" },
    applies_to: { value: "staff" },
    effective_from: { value: "2025-07-01" },
  },
};

describe("benefit charges (rulings 61 and 62)", () => {
  it("shows a mismatch as expected against charged, on the problem list and on the charge", () => {
    render(<ProblemList rows={[{ kind: "charge", charge: benefits, status: status(benefits, [mismatch]) }]} />);
    expect(screen.getByText(/Expected \$360\.00, charged \$366\.00/)).toBeInTheDocument();
  });

  it("shows expected against charged on the charge page's reasons", () => {
    render(<StatusReasons status={status(benefits, [mismatch])} chargeId={benefits.id} chargedCents={benefits.amount_cents} />);
    expect(screen.getByText("Expected $360.00 · charged $366.00")).toBeInTheDocument();
  });

  it("lists the benefit charges waiting on a salary line under its row", () => {
    const failing: Reason = { check: "checklist", problem: "missing_item", text: "An effort report isn't on file.", bucket: "missing_evidence" };
    render(
      <ProblemList
        rows={[{ kind: "charge", charge: salary, status: status(salary, [failing]), waiting_charge_ids: ["chg-benefits", "chg-unknown"] }]}
        charges={{ [benefits.id]: benefits }}
      />,
    );
    const waiting = screen.getByRole("list", { name: "Benefit charges waiting on this line" });
    const links = within(waiting).getAllByRole("link");
    expect(links.map((a) => [a.textContent, a.getAttribute("href")])).toEqual([
      ["L-2002 · Benefits, March", "/grants/grant-sample/charges/chg-benefits"],
      ["Benefit charge 2", "/grants/grant-sample/charges/chg-unknown"],
    ]);
  });

  it("shows a checklist item filled by recalculation with its rate term and salary lines, and no links", () => {
    const entry: ChecklistEntry = {
      default_item: "benefits",
      added_by: "default",
      needed: "Benefits that match the rate times the salary lines",
      filled: true,
      rate_id: "rec-rate",
      charge_ids: ["chg-salary", "chg-salary-2"],
    };
    render(
      <EvidenceChecklist checklist={[entry]} links={[]} waiting={[]} records={{ [rate.id]: rate }} files={{}} grantId="grant-sample" />,
    );
    const item = screen.getByRole("list", { name: "Evidence checklist" });
    expect(within(item).getByText(/Recalculated from/)).toBeInTheDocument();
    expect(within(item).getByRole("link", { name: "Staff benefits (0.366)" })).toHaveAttribute("href", "/grants/grant-sample/records/rec-rate");
    expect(within(item).getByRole("link", { name: "salary line 2" })).toHaveAttribute("href", "/grants/grant-sample/charges/chg-salary-2");
    expect(within(item).queryByText(/Filled by/)).toBeNull();
  });
});
