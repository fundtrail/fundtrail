import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { BudgetLineView, BudgetView } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { SAMPLE_GRANT_ID } from "@/lib/api/fixtures/sample";
import { BudgetFigures } from "./BudgetFigures";

/** The sample's budget, with its lines as given, in its order. */
async function sampleBudget(): Promise<BudgetView> {
  return (await createFakeApiClient().getGrant(SAMPLE_GRANT_ID)).budget;
}

const named = (budget: BudgetView, name: string): BudgetLineView => budget.lines.find((l) => l.line.data.name.value === name)!;

/** The names of a list's own lines, in order, without their sub-lines. */
function ownNames(list: HTMLElement): string[] {
  return [...list.children].map((li) => li.querySelector("span")?.firstChild?.textContent ?? "");
}

describe("BudgetFigures and sub-lines (ruling 74)", () => {
  it("shows every line in the server's order when none is a sub-line", async () => {
    const budget = await sampleBudget();
    render(<BudgetFigures budget={budget} />);
    const list = screen.getAllByRole("list")[0];
    expect(ownNames(list)).toEqual(budget.lines.map((l) => l.line.data.name.value));
  });

  it("nests a sub-line under its parent line, keeps an orphan at the top level, keeps the order, and adds nothing up", async () => {
    const base = await sampleBudget();
    const parent = named(base, "Other Direct Costs");
    const budget: BudgetView = {
      ...base,
      lines: base.lines.map((l) => {
        const name = l.line.data.name.value;
        // "Other" sits inside Other Direct Costs; Materials names a parent that isn't on the list.
        if (name === "Other") return { ...l, parent: parent.line.data.category };
        if (name === "Materials and Supplies") return { ...l, parent: "travel" };
        return l;
      }),
    };
    render(<BudgetFigures budget={budget} />);

    const [top] = screen.getAllByRole("list");
    expect(ownNames(top)).toEqual(["Participant Support Costs", "Other Direct Costs", "Materials and Supplies"]);
    const within_ = screen.getByRole("list", { name: "Within Other Direct Costs" });
    expect(ownNames(within_)).toEqual(["Other"]);
    // Each line shows its own amounts, as given: the parent's aren't changed, and no total is drawn.
    const parentRow = within_.closest("li")!;
    expect(within(parentRow).getByText("$3,420.00 of $100,000.00")).toBeInTheDocument();
    expect(within(within_).getByText("$2,180.00 of $60,000.00")).toBeInTheDocument();
    expect(screen.queryByText(/total/i)).toBeNull();
  });

  it("keeps the server's order among several sub-lines of one parent", async () => {
    const base = await sampleBudget();
    const parent = named(base, "Participant Support Costs");
    const budget: BudgetView = {
      ...base,
      lines: base.lines.map((l) => (l === parent ? l : { ...l, parent: parent.line.data.category })),
    };
    render(<BudgetFigures budget={budget} />);
    const subs = screen.getByRole("list", { name: "Within Participant Support Costs" });
    expect(ownNames(subs)).toEqual(["Other Direct Costs", "Materials and Supplies", "Other"]);
  });
});
