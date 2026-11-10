import { describe, expect, it } from "vitest";
import { routes } from "./routes";

describe("routes", () => {
  it("opens a file in the viewer, at a record's value when given one", () => {
    expect(routes.file("g", "f")).toBe("/grants/g/files/f");
    expect(routes.file("g", "f", { recordId: "rec-link-1" })).toBe("/grants/g/files/f?record=rec-link-1");
    expect(routes.file("g", "f", { recordId: "rec-link-1", value: "part" })).toBe("/grants/g/files/f?record=rec-link-1&value=part");
    expect(routes.file("g", "f", { recordId: "rec-1", value: "items[0].amount" })).toBe("/grants/g/files/f?record=rec-1&value=items%5B0%5D.amount");
  });

  it("names the evidence list and the confirm screen", () => {
    expect(routes.evidence("g")).toBe("/grants/g/files");
    expect(routes.confirmValues("g", "f", "rec-1")).toBe("/grants/g/files/f/confirm?record=rec-1");
  });

  it("encodes IDs", () => {
    expect(routes.charge("g/1", "c 2")).toBe("/grants/g%2F1/charges/c%202");
  });
});
