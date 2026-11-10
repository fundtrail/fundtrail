import { describe, expect, it } from "vitest";
import { buildTypedTerm, parseCents } from "./TypeTermForm";

describe("buildTypedTerm", () => {
  it("sends a rate as a plain number", () => {
    expect(buildTypedTerm("rate", { name: "Fringe benefits", rate: "0.366" })).toEqual({
      data: { kind: "rate", name: { value: "Fringe benefits" }, rate: { value: "0.366" } },
    });
  });

  it("refuses a rate that isn't a number before sending", () => {
    expect(buildTypedTerm("rate", { name: "Fringe benefits", rate: "36.6%" })).toEqual({ problems: ["Value isn't a number."] });
  });

  it("reads an amount into cents and names a missing required value", () => {
    expect(buildTypedTerm("budget_line", { name: "Travel", amount: "$1,250.50", category: "" })).toEqual({ problems: ["Category is needed."] });
    expect(parseCents("$1,250.50")).toBe(125050);
    expect(parseCents("twelve")).toBeNull();
  });
});
