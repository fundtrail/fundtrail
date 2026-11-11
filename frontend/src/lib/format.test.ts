import { describe, expect, it } from "vitest";
import { percent } from "./format";

describe("percent", () => {
  it("shows a rate stored as a fraction as a percentage", () => {
    expect(percent("0.366")).toBe("36.6%");
    expect(percent("0.08")).toBe("8%");
    expect(percent(0.0765)).toBe("7.65%");
    expect(percent("not a number")).toBe("not a number");
  });
});
