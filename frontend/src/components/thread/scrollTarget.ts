import type { Id, Thread } from "@/lib/api";

/** What the thread's scrolling needs to know: how many entries, and which records wait, in order. */
export interface ThreadShape {
  count: number;
  waiting: Id[];
}

/** Which entry to bring into view: the newest, a waiting record, or none (leave the scroll alone). */
export type ScrollTarget = { to: "newest" } | { to: "record"; id: Id } | { to: "stay" };

export function threadShape(thread: Thread): ThreadShape {
  return {
    count: thread.entries.length,
    waiting: thread.entries.flatMap((e) => (e.kind === "record" && e.state === "waiting" ? [e.record.id] : [])),
  };
}

function sameSet(a: Id[], b: Id[]): boolean {
  return a.length === b.length && a.every((id) => b.includes(id));
}

/**
 * Where the thread scrolls after it renders. When it first opens, or when the
 * set of suggestions and disputes waiting for the accountant changes, the
 * first waiting one comes into view. Otherwise, when an entry arrives, such as
 * the accountant's question or the agent's reply, the newest one does; with
 * nothing new, the scroll stays where the accountant left it.
 */
export function scrollTarget(prev: ThreadShape | null, next: ThreadShape): ScrollTarget {
  const arrived = prev === null || next.count > prev.count;
  if (prev === null || !sameSet(prev.waiting, next.waiting)) {
    if (next.waiting.length > 0) return { to: "record", id: next.waiting[0] };
  }
  return arrived ? { to: "newest" } : { to: "stay" };
}
