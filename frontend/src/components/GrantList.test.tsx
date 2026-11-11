import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { GrantSummary } from "@/lib/api";
import { fakeHarness } from "./setup/testing";
import { GrantList, ReadyBar } from "./GrantList";

function fills(container: HTMLElement) {
  return [...container.querySelectorAll("[data-ready-bar] > span")].map((s) => (s as HTMLElement).style.width);
}

describe("the readiness bar", () => {
  it("draws only the two numbers beside it: ready out of total", () => {
    const { container } = render(<ReadyBar ready={1} total={4} />);
    expect(fills(container)).toEqual(["25%"]);
  });

  it("is an empty track when a grant has no charges", () => {
    const { container } = render(<ReadyBar ready={0} total={0} />);
    expect(fills(container)).toEqual(["0%"]);
  });

  it("agrees with the count where the buckets would not: accepted conflicts count as ready", async () => {
    const { client, Wrapper } = fakeHarness();
    const [sample] = await client.listGrants("ws-sample");
    // Every charge ready for closeout, though some still sit in Possible conflict
    // (accepted with a note) and one Evidence complete charge is counted too.
    const summary: GrantSummary = {
      ...sample!,
      charges_ready: 10,
      charges_total: 10,
      bucket_counts: { possible_conflict: 3, needs_human: 1, missing_evidence: 0, evidence_complete: 6 },
    };
    const { container } = render(<GrantList grants={[summary]} />, { wrapper: Wrapper });
    expect(screen.getByRole("cell", { name: /10 of 10 charges/ })).toBeInTheDocument();
    // One filled segment, all the way across: nothing red over "10 of 10".
    expect(fills(container)).toEqual(["100%"]);
  });
});

describe("the grant list", () => {
  it("is a table of grants, one row each, whose name opens the grant", async () => {
    const { client, Wrapper } = fakeHarness();
    const grants = await client.listGrants("ws-sample");
    render(<GrantList grants={grants} />, { wrapper: Wrapper });
    const table = screen.getByRole("table", { name: "Grants" });
    expect(table).toBeInTheDocument();
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Grant",
      "Ends",
      "Ready for closeout",
      "Problem list",
      "Next closeout date",
    ]);
    // A header row, then one row per grant.
    expect(screen.getAllByRole("row")).toHaveLength(grants.length + 1);
    expect(screen.getByRole("link", { name: "Sediment Microbiome Survey of Example Bay" })).toHaveAttribute(
      "href",
      `/grants/${grants[0]!.grant.id}`,
    );
  });
});
