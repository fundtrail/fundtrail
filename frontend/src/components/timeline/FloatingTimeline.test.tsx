import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiProvider, type GrantSummary } from "@/lib/api";
import { createFakeApiClient } from "@/lib/api/fake";
import { WORKSPACE_ID } from "@/lib/api/fixtures/sample";
import { FAKE_USER, StaticAuthProvider } from "@/lib/auth";
import { clampPlace, SampleTimelineBox, SampleTimelineToggle, useSampleTimelineDock } from "./FloatingTimeline";

const auth = { state: { status: "signed_in" as const, user: FAKE_USER }, fake: true, signIn: async () => {}, signOut: async () => {}, getAccessToken: async () => null };

function Dock({ summary }: { summary: GrantSummary }) {
  const dock = useSampleTimelineDock();
  return (
    <>
      <SampleTimelineToggle dock={dock} />
      <SampleTimelineBox summary={summary} dock={dock} />
    </>
  );
}

async function renderDock() {
  const client = createFakeApiClient();
  const [summary] = await client.listGrants(WORKSPACE_ID);
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <StaticAuthProvider value={auth}>
        <ApiProvider client={client}>{children}</ApiProvider>
      </StaticAuthProvider>
    );
  }
  render(<Dock summary={summary} />, { wrapper: Wrapper });
  await screen.findByRole("heading", { name: "Sample timeline", hidden: true });
}

/** The box: the element the toggle controls. Inside it, the panel is its own region named Sample timeline. */
const box = () => document.querySelector<HTMLElement>(".ft-float")!;
const toggle = () => screen.getByRole("button", { name: "Sample timeline" });
const hide = () => screen.getByRole("button", { name: "Hide" });
const at = () => ({ right: box().style.getPropertyValue("--ft-float-right"), bottom: box().style.getPropertyValue("--ft-float-bottom") });

/** A window of this size, wide or narrow by the 900px rule, and a 480 by 170 box. */
function windowOf(width: number, height: number) {
  vi.stubGlobal("innerWidth", width);
  vi.stubGlobal("innerHeight", height);
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: query === "(min-width: 900px)" && width >= 900, addEventListener() {}, removeEventListener() {} }));
}

/** Presses on `target`, moves the pointer by (dx, dy) on the window, and lets go. */
function drag(target: Element, dx: number, dy: number) {
  fireEvent.pointerDown(target, { button: 0, pointerId: 1, clientX: 500, clientY: 500 });
  fireEvent.pointerMove(window, { pointerId: 1, clientX: 500 + dx / 2, clientY: 500 + dy / 2 });
  fireEvent.pointerMove(window, { pointerId: 1, clientX: 500 + dx, clientY: 500 + dy });
  fireEvent.pointerUp(window, { pointerId: 1, clientX: 500 + dx, clientY: 500 + dy });
}

beforeEach(() => {
  window.localStorage.clear();
  // jsdom has no layout: every element measures 480 by 170.
  vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(480);
  vi.spyOn(HTMLElement.prototype, "offsetHeight", "get").mockReturnValue(170);
  // jsdom has no PointerEvent: a mouse event that carries a pointer ID stands in for it.
  if (typeof window.PointerEvent === "undefined") {
    class FakePointerEvent extends MouseEvent {
      pointerId: number;
      constructor(type: string, init: PointerEventInit = {}) {
        super(type, init);
        this.pointerId = init.pointerId ?? 0;
      }
    }
    vi.stubGlobal("PointerEvent", FakePointerEvent);
  }
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the floating sample timeline", () => {
  it("starts open at the bottom right, its toggle pressed and pointing at it", async () => {
    windowOf(1440, 900);
    await renderDock();
    expect(box()).toBeVisible();
    expect(at()).toEqual({ right: "24px", bottom: "24px" });
    expect(toggle()).toHaveAttribute("aria-expanded", "true");
    expect(toggle()).toHaveAttribute("aria-controls", box().id);
  });

  it("moves when dragged anywhere on the box, and remembers where", async () => {
    windowOf(1440, 900);
    await renderDock();
    drag(box().querySelector(".ft-float__bar")!, -300, -200);
    expect(at()).toEqual({ right: "324px", bottom: "224px" });
    expect(JSON.parse(window.localStorage.getItem("ft.sampleTimeline.place")!)).toEqual({ right: 324, bottom: 224 });
  });

  it("doesn't move when the drag starts on one of its controls, which still work", async () => {
    windowOf(1440, 900);
    await renderDock();
    const more = screen.getByRole("button", { name: "More" });
    drag(more, -300, -200);
    expect(at()).toEqual({ right: "24px", bottom: "24px" });
    fireEvent.click(more);
    expect(screen.getByRole("button", { name: "Less" })).toHaveAttribute("aria-expanded", "true");
  });

  it("treats a press that moves less than 4px as a click, not a drag", async () => {
    windowOf(1440, 900);
    await renderDock();
    drag(box().querySelector(".ft-float__bar")!, -3, 2);
    expect(at()).toEqual({ right: "24px", bottom: "24px" });
  });

  it("moves by the arrow keys on its grip", async () => {
    windowOf(1440, 900);
    await renderDock();
    const grip = screen.getByRole("button", { name: /Move the timeline/ });
    fireEvent.keyDown(grip, { key: "ArrowLeft" });
    fireEvent.keyDown(grip, { key: "ArrowUp" });
    expect(at()).toEqual({ right: "48px", bottom: "48px" });
  });

  it("keeps the whole box on screen however far it's dragged, and when the window shrinks", async () => {
    windowOf(1440, 900);
    await renderDock();
    drag(box().querySelector(".ft-float__bar")!, -5000, -5000);
    // 1440 - 480 - 16 and 900 - 170 - 16: the box's left and top edges sit 16px inside the window.
    expect(at()).toEqual({ right: "944px", bottom: "714px" });
    drag(box().querySelector(".ft-float__bar")!, 5000, 5000);
    expect(at()).toEqual({ right: "16px", bottom: "16px" });
    drag(box().querySelector(".ft-float__bar")!, -600, -400);
    windowOf(1000, 600);
    act(() => void window.dispatchEvent(new Event("resize")));
    expect(at()).toEqual({ right: "504px", bottom: "414px" });
  });

  it("clamps a place to the window", () => {
    const view = { width: 1024, height: 768 };
    const size = { width: 480, height: 600 };
    expect(clampPlace({ right: -50, bottom: 9000 }, size, view)).toEqual({ right: 16, bottom: 152 });
    expect(clampPlace({ right: 100, bottom: 100 }, size, view)).toEqual({ right: 100, bottom: 100 });
    // A box taller than the window keeps its top on screen.
    expect(clampPlace({ right: 100, bottom: 100 }, { width: 480, height: 900 }, view)).toEqual({ right: 100, bottom: 16 });
  });

  it("closes with Hide to the sidebar toggle, and the toggle brings it back where it was", async () => {
    windowOf(1440, 900);
    await renderDock();
    drag(box().querySelector(".ft-float__bar")!, -100, -100);
    fireEvent.click(hide());
    expect(box()).not.toBeVisible();
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(toggle()).toHaveFocus();
    expect(window.localStorage.getItem("ft.sampleTimeline.open")).toBe("0");
    fireEvent.click(toggle());
    expect(box()).toBeVisible();
    expect(hide()).toHaveFocus();
    expect(at()).toEqual({ right: "124px", bottom: "124px" });
    expect(window.localStorage.getItem("ft.sampleTimeline.open")).toBe("1");
  });

  it("starts closed and where it was left when this browser remembers that", async () => {
    windowOf(1440, 900);
    window.localStorage.setItem("ft.sampleTimeline.open", "0");
    window.localStorage.setItem("ft.sampleTimeline.place", JSON.stringify({ right: 200, bottom: 150 }));
    await renderDock();
    expect(box()).not.toBeVisible();
    expect(toggle()).toHaveAttribute("aria-expanded", "false");
    expect(at()).toEqual({ right: "200px", bottom: "150px" });
  });

  it("on a narrow screen opens as a panel at the bottom that doesn't move", async () => {
    windowOf(800, 900);
    await renderDock();
    drag(box().querySelector(".ft-float__bar")!, -300, -200);
    fireEvent.keyDown(screen.getByRole("button", { name: /Move the timeline/ }), { key: "ArrowLeft" });
    expect(at()).toEqual({ right: "24px", bottom: "24px" });
    fireEvent.click(hide());
    expect(box()).not.toBeVisible();
    fireEvent.click(toggle());
    expect(box()).toBeVisible();
  });

  it("still works when this browser won't store anything", async () => {
    windowOf(1440, 900);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    await renderDock();
    expect(box()).toBeVisible();
    drag(box().querySelector(".ft-float__bar")!, -100, -50);
    expect(at()).toEqual({ right: "124px", bottom: "74px" });
    fireEvent.click(hide());
    expect(box()).not.toBeVisible();
    fireEvent.click(toggle());
    expect(box()).toBeVisible();
  });
});
