"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type PointerEvent,
} from "react";
import type { GrantSummary } from "@/lib/api";
import { SampleTimeline } from "./TimelinePanel";
import "./timeline.css";

/**
 * The sample timeline as a box that floats over every page of a sample grant,
 * opened and closed from a toggle in the sidebar (issue 348).
 *
 * Wide screens: the box starts at the bottom right, moves when dragged
 * anywhere outside its controls (or by the arrow keys on its grip), and always
 * stays whole on screen. Narrow screens: it opens as a panel fixed to the
 * bottom of the screen and doesn't move. Where it sits and whether it's open
 * are remembered in this browser only.
 */

const WIDE = "(min-width: 900px)";
const PLACE_KEY = "ft.sampleTimeline.place";
const OPEN_KEY = "ft.sampleTimeline.open";
/** The box keeps at least this far from every edge of the window. */
const EDGE = 16;
/** How far one arrow key moves it. */
const STEP = 24;
/** A press that moves less than this is a click, not a drag. */
const SLOP = 4;
/** Pressing these does what they do; pressing anywhere else on the box drags it. */
const CONTROLS = "a, button:not(.ft-float__grip), input, select, textarea, label, summary, [contenteditable]";

/** Distances from the window's right and bottom edges, in pixels. */
export type Place = { right: number; bottom: number };
const START: Place = { right: 24, bottom: 24 };

function read(key: string): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // A browser that won't store it just starts open, in the corner, next time.
  }
}

function readPlace(): Place {
  try {
    const p = JSON.parse(read(PLACE_KEY) ?? "null") as Partial<Place> | null;
    if (p && Number.isFinite(p.right) && Number.isFinite(p.bottom)) return { right: p.right as number, bottom: p.bottom as number };
  } catch {
    // Unreadable: start in the corner.
  }
  return START;
}

function isWide(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(WIDE).matches;
}

/** Keeps the whole box on screen. */
export function clampPlace(p: Place, size: { width: number; height: number }, view: { width: number; height: number }): Place {
  const maxRight = Math.max(EDGE, view.width - size.width - EDGE);
  const maxBottom = Math.max(EDGE, view.height - size.height - EDGE);
  return {
    right: Math.round(Math.min(Math.max(EDGE, p.right), maxRight)),
    bottom: Math.round(Math.min(Math.max(EDGE, p.bottom), maxBottom)),
  };
}

function clampTo(p: Place, box: HTMLElement | null): Place {
  // A closed box has no size: leave it where it was until it opens.
  if (!box || box.offsetWidth === 0) return p;
  return clampPlace(p, { width: box.offsetWidth, height: box.offsetHeight }, { width: window.innerWidth, height: window.innerHeight });
}

/** Where focus goes after the box opens or closes. */
type FocusTo = "toggle" | "hide" | null;

export type SampleTimelineDock = {
  open: boolean;
  setOpen: (open: boolean, focusTo: FocusTo) => void;
  boxId: string;
  toggleId: string;
  hideId: string;
};

/** Open or closed, shared by the sidebar's toggle and the box's Hide button. */
export function useSampleTimelineDock(): SampleTimelineDock {
  // The shell renders only on the client, after sign-in, so the remembered state is read up front.
  const [open, setOpenState] = useState(() => read(OPEN_KEY) !== "0");
  const boxId = useId();
  const toggleId = useId();
  const hideId = useId();
  const focusTo = useRef<FocusTo>(null);

  useEffect(() => {
    const to = focusTo.current;
    focusTo.current = null;
    if (to) document.getElementById(to === "toggle" ? toggleId : hideId)?.focus();
  }, [open, toggleId, hideId]);

  const setOpen = useCallback((next: boolean, to: FocusTo) => {
    focusTo.current = to;
    setOpenState(next);
    write(OPEN_KEY, next ? "1" : "0");
  }, []);

  return { open, setOpen, boxId, toggleId, hideId };
}

/** The sidebar's toggle, among the grant's pages. It stays there, open or closed. */
export function SampleTimelineToggle({ dock }: { dock: SampleTimelineDock }) {
  return (
    <button
      id={dock.toggleId}
      type="button"
      className="ft-nav__item ft-tl-toggle"
      aria-expanded={dock.open}
      aria-controls={dock.boxId}
      onClick={() => dock.setOpen(!dock.open, dock.open ? null : "hide")}
    >
      <svg
        className="ft-nav__icon"
        width="16"
        height="16"
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        aria-hidden="true"
      >
        <path d="M4.5 8h3" />
        <path d="M10.5 8h1.5" strokeDasharray="1.5 1.5" />
        <circle cx="2.5" cy="8" r="1.5" fill="currentColor" />
        <circle cx="9" cy="8" r="1.5" />
        <circle cx="14" cy="8" r="0.6" fill="currentColor" />
      </svg>
      <span className="ft-nav__text">Sample timeline</span>
      <span className="ft-tl-toggle__switch" aria-hidden="true" />
    </button>
  );
}

/** The box itself, for the open grant when it's a sample grant. */
export function SampleTimelineBox({ summary, dock }: { summary: GrantSummary; dock: SampleTimelineDock }) {
  const [place, setPlace] = useState<Place>(readPlace);
  const [dragging, setDragging] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; from: Place; moving: boolean; id: number } | null>(null);
  const { open } = dock;

  const moveTo = useCallback((next: Place) => {
    const placed = clampTo(next, box.current);
    setPlace(placed);
    write(PLACE_KEY, JSON.stringify(placed));
  }, []);

  // A smaller window, or a box that grew when More opened, keeps the whole box on screen.
  useEffect(() => {
    const el = box.current;
    if (!open || !el) return;
    const keep = () => {
      if (isWide()) setPlace((p) => clampTo(p, el));
    };
    keep();
    window.addEventListener("resize", keep);
    const watch = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(keep);
    watch?.observe(el);
    return () => {
      window.removeEventListener("resize", keep);
      watch?.disconnect();
    };
  }, [open]);

  // A drag in progress listens on the window, so a fast move that leaves the box still moves it.
  const stopDrag = useRef<(() => void) | null>(null);
  useEffect(() => () => stopDrag.current?.(), []);

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (e.button !== 0 || drag.current || !isWide() || (e.target as Element).closest(CONTROLS)) return;
    drag.current = { x: e.clientX, y: e.clientY, from: place, moving: false, id: e.pointerId };
    const onMove = (ev: globalThis.PointerEvent) => {
      const d = drag.current;
      if (!d || d.id !== ev.pointerId) return;
      const dx = ev.clientX - d.x;
      const dy = ev.clientY - d.y;
      if (!d.moving) {
        if (Math.abs(dx) < SLOP && Math.abs(dy) < SLOP) return;
        d.moving = true;
        setDragging(true);
        window.getSelection()?.removeAllRanges();
      }
      ev.preventDefault();
      setPlace(clampTo({ right: d.from.right - dx, bottom: d.from.bottom - dy }, box.current));
    };
    const onUp = (ev: globalThis.PointerEvent) => {
      const d = drag.current;
      if (!d || d.id !== ev.pointerId) return;
      stop();
      if (d.moving) moveTo({ right: d.from.right - (ev.clientX - d.x), bottom: d.from.bottom - (ev.clientY - d.y) });
    };
    const stop = () => {
      drag.current = null;
      stopDrag.current = null;
      setDragging(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
    stopDrag.current = stop;
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  }
  function onGripKey(e: KeyboardEvent<HTMLButtonElement>) {
    const by: Record<string, [number, number]> = {
      ArrowLeft: [STEP, 0],
      ArrowRight: [-STEP, 0],
      ArrowUp: [0, STEP],
      ArrowDown: [0, -STEP],
    };
    const delta = by[e.key];
    if (!delta || !isWide()) return;
    e.preventDefault();
    moveTo({ right: place.right + delta[0], bottom: place.bottom + delta[1] });
  }

  const at = { "--ft-float-right": `${place.right}px`, "--ft-float-bottom": `${place.bottom}px` } as CSSProperties;
  return (
    <div
      ref={box}
      id={dock.boxId}
      className="ft-float"
      style={at}
      hidden={!open}
      data-dragging={dragging || undefined}
      onPointerDown={onPointerDown}
    >
      <div className="ft-float__bar">
        <button
          type="button"
          className="ft-float__grip"
          aria-label="Move the timeline: drag the box, or use the arrow keys here"
          title="Drag to move"
          onKeyDown={onGripKey}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
            <g fill="currentColor">
              <circle cx="5" cy="4" r="1.25" />
              <circle cx="11" cy="4" r="1.25" />
              <circle cx="5" cy="8" r="1.25" />
              <circle cx="11" cy="8" r="1.25" />
              <circle cx="5" cy="12" r="1.25" />
              <circle cx="11" cy="12" r="1.25" />
            </g>
          </svg>
        </button>
        <button id={dock.hideId} type="button" className="ft-float__hide" onClick={() => dock.setOpen(false, "toggle")}>
          Hide
        </button>
      </div>
      <div className="ft-float__body">
        <SampleTimeline summary={summary} />
      </div>
    </div>
  );
}
