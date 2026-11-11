"use client";

import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from "react";

/**
 * The sample timeline as a floating box on wide screens: it starts over the
 * page's bottom right corner, moves when dragged anywhere outside its controls
 * (or by the arrow keys on its handle), always stays whole on screen, and hides
 * to a small button at the top left of the page that brings it back. Where it
 * sits and whether it's hidden are remembered in this browser only. On narrow
 * screens it stays in the page, where it was before.
 */

const WIDE = "(min-width: 900px)";
const KEY = "ft.timelineFloat";
const EDGE = 16;
const STEP = 24;
/** A press that moves less than this is a click, not a drag. */
const SLOP = 4;
/** Pressing these does what they do; pressing anywhere else on the box drags it. */
const CONTROLS = "a, button:not(.ft-float__handle), input, select, textarea, label, summary, [contenteditable]";

type Place = { right: number; bottom: number; hidden: boolean };
const START: Place = { right: 24, bottom: 24, hidden: false };

function readPlace(): Place {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return START;
    const p = JSON.parse(raw) as Partial<Place>;
    return {
      right: typeof p.right === "number" ? p.right : START.right,
      bottom: typeof p.bottom === "number" ? p.bottom : START.bottom,
      hidden: p.hidden === true,
    };
  } catch {
    return START;
  }
}

function savePlace(p: Place) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    // A browser that won't store it just starts in the corner next time.
  }
}

function useWide(): boolean {
  const [wide, setWide] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(WIDE);
    const update = () => setWide(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  return wide;
}

/** Keeps the whole box on screen. */
function clamp(p: Place, box: HTMLElement | null): Place {
  const w = box?.offsetWidth ?? 0;
  const h = box?.offsetHeight ?? 0;
  const maxRight = Math.max(EDGE, window.innerWidth - w - EDGE);
  const maxBottom = Math.max(EDGE, window.innerHeight - h - EDGE);
  return { ...p, right: Math.min(Math.max(EDGE, p.right), maxRight), bottom: Math.min(Math.max(EDGE, p.bottom), maxBottom) };
}

export function FloatingTimeline({ children }: { children: ReactNode }) {
  const wide = useWide();
  const [place, setPlace] = useState<Place>(START);
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; right: number; bottom: number; moving: boolean; id: number } | null>(null);
  const showButton = useRef<HTMLButtonElement>(null);
  const hideButton = useRef<HTMLButtonElement>(null);
  const moved = useRef(false);

  useEffect(() => setPlace(readPlace()), []);

  const update = useCallback((next: Place) => {
    const placed = clamp(next, box.current);
    setPlace(placed);
    savePlace(placed);
  }, []);

  // A smaller window keeps the box on screen.
  useEffect(() => {
    if (!wide) return;
    const onResize = () => setPlace((p) => clamp(p, box.current));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [wide]);

  // The box grows when More opens: keep all of it on screen.
  useEffect(() => {
    const el = box.current;
    if (!wide || place.hidden || !el || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(() => setPlace((p) => clamp(p, el)));
    watch.observe(el);
    return () => watch.disconnect();
  }, [wide, place.hidden]);

  // Focus follows the box when it hides or comes back, but not on the first render.
  useEffect(() => {
    if (!moved.current) return;
    (place.hidden ? showButton : hideButton).current?.focus();
  }, [place.hidden]);

  if (!wide) return <div className="ft-float ft-float--inline">{children}</div>;

  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (e.button !== 0 || (e.target as Element).closest(CONTROLS)) return;
    drag.current = { x: e.clientX, y: e.clientY, right: place.right, bottom: place.bottom, moving: false, id: e.pointerId };
  }
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    const dx = e.clientX - d.x;
    const dy = e.clientY - d.y;
    if (!d.moving) {
      if (Math.abs(dx) < SLOP && Math.abs(dy) < SLOP) return;
      d.moving = true;
      e.currentTarget.setPointerCapture?.(e.pointerId);
      window.getSelection()?.removeAllRanges();
    }
    e.preventDefault();
    setPlace((p) => clamp({ ...p, right: d.right - dx, bottom: d.bottom - dy }, box.current));
  }
  function onPointerUp(e: PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    drag.current = null;
    if (!d.moving) return;
    e.currentTarget.releasePointerCapture?.(e.pointerId);
    setPlace((p) => {
      savePlace(p);
      return p;
    });
  }
  function onHandleKey(e: KeyboardEvent<HTMLButtonElement>) {
    const by: Record<string, [number, number]> = {
      ArrowLeft: [STEP, 0],
      ArrowRight: [-STEP, 0],
      ArrowUp: [0, STEP],
      ArrowDown: [0, -STEP],
    };
    const delta = by[e.key];
    if (!delta) return;
    e.preventDefault();
    update({ ...place, right: place.right + delta[0], bottom: place.bottom + delta[1] });
  }
  function setHidden(hidden: boolean) {
    moved.current = true;
    update({ ...place, hidden });
  }

  const at = { right: place.right, bottom: place.bottom };
  if (place.hidden) {
    return (
      <button ref={showButton} type="button" className="ft-float__show" aria-expanded="false" onClick={() => setHidden(false)}>
        <span className="ft-float__dot" aria-hidden="true" />
        Sample timeline
      </button>
    );
  }
  return (
    <div
      ref={box}
      className="ft-float ft-float--floating"
      style={at}
      role="region"
      aria-label="Sample timeline"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className="ft-float__bar">
        <button
          type="button"
          className="ft-float__handle"
          aria-label="Move the timeline. Drag the box, or use the arrow keys here."
          title="Drag to move"
          onKeyDown={onHandleKey}
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
        <button ref={hideButton} type="button" className="ft-float__hide" aria-expanded="true" onClick={() => setHidden(true)}>
          Hide
        </button>
      </div>
      <div className="ft-float__body">{children}</div>
    </div>
  );
}
