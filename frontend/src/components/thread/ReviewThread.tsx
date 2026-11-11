"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type {
  ChargeStatus,
  ChecklistEntry,
  Citation,
  EvidenceFile,
  FtRecord,
  Id,
  Reason,
  RecordState,
  RecordStatus,
  SuggestionView,
  Thread,
  ThreadEntry,
} from "@/lib/api";
import { date, recordKindLabel } from "@/lib/format";
import { BucketBadge } from "../BucketBadge";
import { ANSWER_LABELS, AUTHOR_LABELS, field } from "../charge/labels";
import { DisputeBox, errorLines, SuggestionBox, type Decision, type DecisionMade, type OnDecide } from "./Decide";
import { changeFor } from "./describe";
import { scrollTarget, threadShape, type ThreadShape } from "./scrollTarget";
import styles from "./thread.module.css";

export interface ThreadContext {
  records: Record<Id, FtRecord>;
  files: Record<Id, EvidenceFile>;
  /** The charge's checklist, to name an item a removal is about. Empty for a record's thread. */
  checklist: ChecklistEntry[];
  /** The charge's current reasons, to name the check a dispute is about. Empty for a record's thread. */
  reasons: Reason[];
  /** The waiting suggestions with what each would replace. */
  waiting: SuggestionView[];
  quoteHref?: (citation: Citation) => string | undefined;
}

type Decisions = Record<Id, DecisionMade>;

/**
 * The accountant's latest decision on each record, read from their
 * confirmation records in the thread and in the body's records. The latest
 * decision on a record wins (contracts.md section 1). Two decisions at the
 * same clock time, which the demo clock makes common, are told apart by the
 * server's order: the later entry wins. A confirmation only in the body's
 * records counts after the thread's.
 */
export function decisionsFrom(thread: Thread, records: Record<Id, FtRecord>): Decisions {
  const inThread = thread.entries.flatMap((e) => (e.kind === "record" ? [e.record] : []));
  const seen = new Set(inThread.map((r) => r.id));
  const confirmations = [...inThread, ...Object.values(records).filter((r) => !seen.has(r.id))].filter(
    (r) => r.author === "user" && r.data.kind === "confirmation",
  );
  const out: Decisions = {};
  for (const c of confirmations) {
    const decision = field<Decision>(c, "decision") ?? "confirmed";
    for (const id of field<Id[]>(c, "record_ids") ?? []) {
      const known = out[id];
      if (!known || known.at <= c.written_at) out[id] = { decision, at: c.written_at };
    }
  }
  return out;
}

function isChargeStatus(status: ChargeStatus | RecordStatus | { problems: unknown }): status is ChargeStatus {
  return "bucket" in status;
}

/** Code's entry: the checks' result when the status changed, in the server's words. Passes are left out. */
function StatusBody({ status }: { status: ChargeStatus | RecordStatus }) {
  if (isChargeStatus(status)) {
    const failing = status.reasons.filter((r) => r.bucket !== "evidence_complete");
    return (
      <>
        <p>
          <BucketBadge bucket={status.bucket} />
        </p>
        {failing.length > 0 && (
          <ul className={styles.reasons}>
            {failing.map((r) => (
              <li key={`${r.check}:${r.problem}`}>{r.text}</li>
            ))}
          </ul>
        )}
      </>
    );
  }
  return (
    <ul className={styles.reasons}>
      {status.problems.map((p) => (
        <li key={`${p.check}:${p.problem}`}>{p.text}</li>
      ))}
    </ul>
  );
}

/** The accountant's decision, named plainly by kind. */
function DecisionBody({ record, ctx }: { record: FtRecord; ctx: ThreadContext }) {
  const kind = record.data.kind;
  if (kind === "confirmation") {
    const ids = field<Id[]>(record, "record_ids") ?? [];
    const decided = field<string>(record, "decision") === "rejected" ? "Rejected" : "Accepted";
    const names = ids.map((id) => (ctx.records[id] ? recordKindLabel(ctx.records[id].data.kind).toLowerCase() : "a record"));
    return (
      <p>
        {decided} {names.join(", ")}
      </p>
    );
  }
  if (kind === "accepted_reason" || kind === "snooze") {
    const until = field<string>(record, "until");
    return (
      <p>
        {kind === "snooze" ? `Snoozed until ${until ? date(until) : "a date"}` : "Accepted a reason"}
        {field<string>(record, "note") && <>: {field<string>(record, "note")}</>}
      </p>
    );
  }
  if (kind === "judgment") {
    const answer = field<string>(record, "answer") ?? "";
    return (
      <p>
        Answered {ANSWER_LABELS[answer] ?? answer}: {field<string>(record, "reasoning")}
      </p>
    );
  }
  return <p>{recordKindLabel(kind)}</p>;
}

function RecordBody({
  record,
  state,
  ctx,
  decisions,
  onDecide,
}: {
  record: FtRecord;
  state: RecordState;
  ctx: ThreadContext;
  decisions: Decisions;
  onDecide?: OnDecide;
}) {
  if (record.author === "user") return <DecisionBody record={record} ctx={ctx} />;
  const decision = decisions[record.id] ?? null;
  if (record.data.kind === "dispute") {
    const check = field<string>(record, "check");
    const reason = ctx.reasons.find((r) => r.dispute_id === record.id) ?? ctx.reasons.find((r) => r.check === check && r.bucket !== "evidence_complete");
    return (
      <DisputeBox
        record={record}
        reasonText={reason?.text ?? null}
        state={state}
        decision={decision}
        files={ctx.files}
        quoteHref={ctx.quoteHref}
        onDecide={onDecide}
      />
    );
  }
  const view = ctx.waiting.find((w) => w.record.id === record.id);
  const replaces = view?.replaces ?? (record.replaces_id ? (ctx.records[record.replaces_id] ?? null) : null);
  const change = changeFor(view, record, replaces, ctx);
  return <SuggestionBox record={record} change={change} state={state} decision={decision} onDecide={onDecide} />;
}

function entryWho(entry: ThreadEntry): { who: "code" | "agent" | "user"; at: string } {
  switch (entry.kind) {
    case "status":
      return { who: "code", at: entry.entry.changed_at };
    case "message":
      return { who: entry.message.author, at: entry.message.written_at };
    case "record":
      return { who: entry.record.author, at: entry.record.written_at };
  }
}

function entryKey(entry: ThreadEntry, i: number): string {
  switch (entry.kind) {
    case "status":
      return `status:${entry.entry.changed_at}:${i}`;
    case "message":
      return `message:${entry.message.id}`;
    case "record":
      return `record:${entry.record.id}`;
  }
}

function Entry({ entry, ctx, decisions, onDecide }: { entry: ThreadEntry; ctx: ThreadContext; decisions: Decisions; onDecide?: OnDecide }) {
  const { who, at } = entryWho(entry);
  return (
    <li
      className={styles.entry}
      data-kind={entry.kind}
      data-who={who}
      data-waiting={(entry.kind === "record" && entry.state === "waiting") || undefined}
      data-record={entry.kind === "record" ? entry.record.id : undefined}
    >
      <div className={styles.who} data-who={who}>
        <span className={styles.whoName}>{who === "code" ? "Code" : AUTHOR_LABELS[who]}</span>
        <span className="ft-caption">{date(at)}</span>
      </div>
      <div className={styles.body}>
        {entry.kind === "status" && <StatusBody status={entry.entry.status as ChargeStatus | RecordStatus} />}
        {entry.kind === "message" && <p>{entry.message.text}</p>}
        {entry.kind === "record" && <RecordBody record={entry.record} state={entry.state} ctx={ctx} decisions={decisions} onDecide={onDecide} />}
      </div>
    </li>
  );
}

/** What the agent is doing for this thread, from the run that will reach it. */
function AgentBusy({ thread }: { thread: Thread }) {
  const run = thread.agent_run;
  if (!run) return null;
  const text = run.status === "running" ? "The agent is working on this now." : "Queued for the agent.";
  return (
    <p className={styles.busy} role="status" aria-live="polite">
      {text}
    </p>
  );
}

/** The box at the bottom of a thread for asking the agent. */
function AskBox({ about, onAsk }: { about: string; onAsk: (text: string) => Promise<void> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  // Never sends twice at once: `busy` is state, so two sends in the same task
  // (before a re-render) both see it false. A send made while one is in flight
  // does nothing at all: no second message, no error line, and the typed text
  // stays. Set before `onAsk` is called, released in `finally`.
  const inFlight = useRef(false);

  async function send() {
    const message = text.trim();
    if (!message || busy || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErrors([]);
    try {
      await onAsk(message);
      setText("");
    } catch (error) {
      setErrors(errorLines(error));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void send();
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      void send();
    }
  }
  return (
    <form className={styles.ask} onSubmit={submit}>
      <label className="ft-sr" htmlFor="ask-agent">
        Ask the agent about {about}
      </label>
      <div className={styles.askRow}>
        <textarea
          id="ask-agent"
          rows={1}
          placeholder={`Ask the agent about ${about}`}
          aria-describedby="ask-agent-help"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={keyDown}
          disabled={busy}
        />
        <button type="submit" className="ft-btn ft-btn--sm" disabled={busy || text.trim() === ""}>
          Send
        </button>
      </div>
      <p id="ask-agent-help" className={styles.help}>
        The agent answers about {about} only. Any change it proposes comes back as a suggestion for you to accept or reject.
      </p>
      {errors.length > 0 && (
        <ul className="ft-error" role="alert">
          {errors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}
    </form>
  );
}

/**
 * A charge's or a record's review thread, top to bottom in the server's order:
 * code's reasons, the agent's comments, suggestions and disputes, the
 * accountant's replies and decisions, and a box to ask the agent.
 */
export function ReviewThread({
  thread,
  about,
  ctx,
  onDecide,
  onAsk,
}: {
  thread: Thread;
  /** What the thread is about, for the ask box: "L-1002", for example. */
  about: string;
  ctx: ThreadContext;
  onDecide?: OnDecide;
  onAsk: (text: string) => Promise<void>;
}) {
  const decisions = decisionsFrom(thread, ctx.records);
  const scroller = useRef<HTMLDivElement>(null);
  const shown = useRef<ThreadShape | null>(null);
  // Newest entry last. scrollTarget decides which entry comes into view, and
  // leaves the scroll alone when a refetch brings nothing new.
  useEffect(() => {
    const el = scroller.current;
    const next = threadShape(thread);
    const target = scrollTarget(shown.current, next);
    shown.current = next;
    if (!el || target.to === "stay") return;
    const entry =
      target.to === "record" ? [...el.querySelectorAll<HTMLElement>("[data-record]")].find((n) => n.dataset.record === target.id) : undefined;
    // The scroll area is positioned, so an entry's offsetTop is measured from its top.
    el.scrollTop = entry ? Math.max(0, entry.offsetTop - 12) : el.scrollHeight;
  }, [thread]);
  return (
    <div className={styles.thread}>
      <div className={styles.scroll} ref={scroller}>
      {thread.entries.length === 0 ? (
        <p className={styles.empty}>Nothing in this thread yet.</p>
      ) : (
        <ol className={styles.entries} aria-label="Review thread">
          {thread.entries.map((entry, i) => (
            <Entry key={entryKey(entry, i)} entry={entry} ctx={ctx} decisions={decisions} onDecide={onDecide} />
          ))}
          </ol>
        )}
      </div>
      <div className={styles.foot}>
        <AgentBusy thread={thread} />
        <AskBox about={about} onAsk={onAsk} />
      </div>
    </div>
  );
}
