import { describe, expect, it } from "vitest";
import { scrollTarget } from "./scrollTarget";

describe("scrollTarget", () => {
  it("opens on the newest entry when nothing waits", () => {
    expect(scrollTarget(null, { count: 4, waiting: [] })).toEqual({ to: "newest" });
  });

  it("opens on the first waiting suggestion or dispute", () => {
    expect(scrollTarget(null, { count: 6, waiting: ["r-old", "r-new"] })).toEqual({ to: "record", id: "r-old" });
  });

  it("goes to the newest entry when the accountant asks or the agent replies while something waits", () => {
    const before = { count: 6, waiting: ["r-old"] };
    expect(scrollTarget(before, { count: 7, waiting: ["r-old"] })).toEqual({ to: "newest" });
    expect(scrollTarget({ count: 7, waiting: ["r-old"] }, { count: 8, waiting: ["r-old"] })).toEqual({ to: "newest" });
  });

  it("brings the first waiting one into view when the waiting set changes", () => {
    expect(scrollTarget({ count: 6, waiting: [] }, { count: 7, waiting: ["r-new"] })).toEqual({ to: "record", id: "r-new" });
    expect(scrollTarget({ count: 7, waiting: ["r-a", "r-b"] }, { count: 8, waiting: ["r-b"] })).toEqual({ to: "record", id: "r-b" });
  });

  it("goes to the newest entry when the last waiting one is decided", () => {
    expect(scrollTarget({ count: 7, waiting: ["r-a"] }, { count: 8, waiting: [] })).toEqual({ to: "newest" });
  });

  it("leaves the scroll alone when a refetch brings nothing new", () => {
    expect(scrollTarget({ count: 7, waiting: ["r-a"] }, { count: 7, waiting: ["r-a"] })).toEqual({ to: "stay" });
  });
});
