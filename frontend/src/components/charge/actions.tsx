"use client";

// The accountant's actions on a charge. Each one writes a record through
// POST /grants/{grant_id}/records and changes nothing on the page itself: the
// screen refetches after the write and shows the server's result. A write the
// server refuses shows its problems and keeps what was typed.

import { useState, type FormEvent, type ReactNode } from "react";
import type { Answer, ChecklistEntry, FtRecord, Id, NewRecordInput, OpenQuestion, Problem, Question, Reason } from "@/lib/api";
import { errorLines } from "../thread/Decide";
import type { OnWrite } from "../thread/useThreadActions";
import { ANSWER_LABELS, field, QUESTION_LABELS } from "./labels";
import styles from "./charge.module.css";

/** Runs one write, with its busy state and the lines to show if it's refused. */
function useWrite(onWrite: OnWrite) {
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  async function run(input: NewRecordInput): Promise<boolean> {
    setBusy(true);
    setErrors([]);
    try {
      await onWrite(input);
      return true;
    } catch (error) {
      setErrors(errorLines(error));
      return false;
    } finally {
      setBusy(false);
    }
  }
  return { busy, errors, run };
}

function Errors({ errors }: { errors: string[] }) {
  if (errors.length === 0) return null;
  return (
    <ul className="ft-error" role="alert">
      {errors.map((e, i) => (
        <li key={i}>{e}</li>
      ))}
    </ul>
  );
}

/** A button that opens a small form in place, and closes it after a write goes through. */
function Opener({ label, children }: { label: string; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  if (!open) {
    return (
      <div className={styles.actions}>
        <button type="button" className="ft-btn ft-btn--sm" onClick={() => setOpen(true)}>
          {label}
        </button>
      </div>
    );
  }
  return <>{children(() => setOpen(false))}</>;
}

function FormButtons({ busy, submit, onCancel }: { busy: boolean; submit: string; onCancel: () => void }) {
  return (
    <div className={styles.actions}>
      <button type="submit" className="ft-btn ft-btn--sm" disabled={busy}>
        {submit}
      </button>
      <button type="button" className="ft-btn ft-btn--sm" onClick={onCancel} disabled={busy}>
        Cancel
      </button>
    </div>
  );
}

/** "$1,800.00" or "1800" to cents; null when it isn't an amount. */
export function parseDollars(text: string): number | null {
  const clean = text.replace(/[$,\s]/g, "");
  const match = /^(-?)(\d+)(?:\.(\d{1,2}))?$/.exec(clean);
  if (!match) return null;
  const cents = Number(match[2]) * 100 + Number((match[3] ?? "").padEnd(2, "0"));
  return match[1] ? -cents : cents;
}

// --- Answering a question, or overruling an answer ---

const ANSWERS: Answer[] = ["supports", "contradicts", "unsure"];

/**
 * The accountant's own answer to one question about the charge. Over an
 * existing answer it replaces it, which is how they overrule the agent or
 * change their own (contracts.md section 4).
 */
export function AnswerForm({
  chargeId,
  question,
  recordId,
  text,
  replaces,
  label,
  onWrite,
}: {
  chargeId: Id;
  question: Question;
  recordId?: Id | null;
  /** The question as asked: the answer's own text, or product.md's wording of an open question. */
  text: string;
  replaces?: FtRecord | null;
  label: string;
  onWrite: OnWrite;
}) {
  const write = useWrite(onWrite);
  const [answer, setAnswer] = useState<Answer | "">("");
  const [reasoning, setReasoning] = useState("");
  const [missing, setMissing] = useState(false);
  const name = `answer-${replaces?.id ?? `${question}-${recordId ?? "charge"}`}`;

  return (
    <Opener label={label}>
      {(close) => {
        async function submit(event: FormEvent) {
          event.preventDefault();
          if (!answer || !reasoning.trim()) {
            setMissing(true);
            return;
          }
          const ok = await write.run({
            data: {
              kind: "judgment",
              charge_id: chargeId || null,
              question,
              record_id: recordId ?? null,
              // An answer about a file keeps naming it when overruled.
              ...(field<Id | null>(replaces, "file_id") ? { file_id: field<Id>(replaces, "file_id") } : {}),
              text,
              answer,
              reasoning: reasoning.trim(),
            },
            replaces_id: replaces?.id ?? null,
          });
          if (ok) close();
        }
        return (
          <form className={styles.form} onSubmit={submit} aria-label={label}>
            <fieldset className={styles.choices}>
              <legend className="ft-label">Your answer</legend>
              {ANSWERS.map((a) => (
                <label key={a}>
                  <input type="radio" name={name} value={a} checked={answer === a} onChange={() => setAnswer(a)} /> {ANSWER_LABELS[a]}
                </label>
              ))}
            </fieldset>
            <label className="ft-label" htmlFor={`${name}-reasoning`}>
              Your reasoning
            </label>
            <textarea id={`${name}-reasoning`} value={reasoning} onChange={(e) => setReasoning(e.target.value)} />
            {missing && (!answer || !reasoning.trim()) && <p className="ft-error">Choose an answer and write your reasoning.</p>}
            <FormButtons busy={write.busy} submit="Save answer" onCancel={close} />
            <Errors errors={write.errors} />
          </form>
        );
      }}
    </Opener>
  );
}

/**
 * The answer form for a question still open. It's offered on every open
 * question, whichever side the server says answers it (`answer_by`): the
 * accountant has the last word and can answer any of them themselves
 * (product call 42, settling PR 128's choice 1).
 */
export function AnswerOpenQuestion({ chargeId, question, onWrite }: { chargeId: Id; question: OpenQuestion; onWrite: OnWrite }) {
  return (
    <AnswerForm
      chargeId={chargeId}
      question={question.question}
      recordId={question.record_id ?? null}
      text={QUESTION_LABELS[question.question] ?? question.question}
      label="Answer"
      onWrite={onWrite}
    />
  );
}

/** Overrule an answer: the agent's, or change the accountant's own. Settling a flag is answering it. */
export function OverruleAnswer({ judgment, onWrite }: { judgment: FtRecord; onWrite: OnWrite }) {
  const question = field<Question>(judgment, "question") ?? "flag";
  const byAgent = judgment.author === "agent";
  const label = !byAgent ? "Change your answer" : question === "flag" ? "Answer the flag" : "Overrule";
  return (
    <AnswerForm
      chargeId={field<Id>(judgment, "charge_id") ?? ""}
      question={question}
      recordId={field<Id | null>(judgment, "record_id") ?? null}
      text={field<string>(judgment, "text") ?? QUESTION_LABELS[question] ?? question}
      replaces={judgment}
      label={label}
      onWrite={onWrite}
    />
  );
}

// --- The checklist ---

/** Adds an item to the charge's checklist. The accountant's item takes effect right away. */
export function AddChecklistItem({ chargeId, onWrite }: { chargeId: Id; onWrite: OnWrite }) {
  const write = useWrite(onWrite);
  const [needed, setNeeded] = useState("");
  const [amount, setAmount] = useState("");
  const [expected, setExpected] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  return (
    <Opener label="Add item">
      {(close) => {
        async function submit(event: FormEvent) {
          event.preventDefault();
          const cents = amount.trim() ? parseDollars(amount) : null;
          if (!needed.trim()) return setProblem("Say what's needed.");
          if (amount.trim() && cents === null) return setProblem("Write the amount as dollars, for example 1,800.00.");
          setProblem(null);
          const ok = await write.run({
            data: {
              kind: "checklist_item",
              charge_id: chargeId,
              needed: needed.trim(),
              amount_cents: cents,
              expected_by: expected || null,
            },
          });
          if (ok) {
            setNeeded("");
            setAmount("");
            setExpected("");
            close();
          }
        }
        return (
          <form className={styles.form} onSubmit={submit} aria-label="Add a checklist item">
            <label className="ft-label" htmlFor="item-needed">
              What&apos;s needed
            </label>
            <input id="item-needed" value={needed} onChange={(e) => setNeeded(e.target.value)} />
            <label className="ft-label" htmlFor="item-amount">
              Amount (optional)
            </label>
            <input id="item-amount" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
            <label className="ft-label" htmlFor="item-expected">
              Expected by (optional)
            </label>
            <input id="item-expected" type="date" value={expected} onChange={(e) => setExpected(e.target.value)} />
            {problem && <p className="ft-error">{problem}</p>}
            <FormButtons busy={write.busy} submit="Add item" onCancel={close} />
            <Errors errors={write.errors} />
          </form>
        );
      }}
    </Opener>
  );
}

/** Removes an item from the checklist. The accountant's removal takes effect right away. */
export function RemoveChecklistItem({ chargeId, entry, onWrite }: { chargeId: Id; entry: ChecklistEntry; onWrite: OnWrite }) {
  const write = useWrite(onWrite);
  const [reason, setReason] = useState("");
  const id = `remove-${entry.item_record_id ?? entry.default_item}`;
  return (
    <Opener label="Remove">
      {(close) => {
        async function submit(event: FormEvent) {
          event.preventDefault();
          const ok = await write.run({
            data: {
              kind: "checklist_removal",
              charge_id: chargeId,
              item_record_id: entry.item_record_id ?? null,
              default_item: entry.default_item ?? null,
              reason: reason.trim() || null,
            },
          });
          if (ok) close();
        }
        return (
          <form className={styles.form} onSubmit={submit} aria-label={`Remove ${entry.needed}`}>
            <label className="ft-label" htmlFor={id}>
              Why (optional)
            </label>
            <input id={id} value={reason} onChange={(e) => setReason(e.target.value)} />
            <FormButtons busy={write.busy} submit="Remove item" onCancel={close} />
            <Errors errors={write.errors} />
          </form>
        );
      }}
    </Opener>
  );
}

// --- Accepting a reason, and reopening it ---

/**
 * Accepts one reason on the charge with a note. A one-off note is the
 * default; a reusable note applies on its own to similar charges inside the
 * limits code checks (product.md, The problem list).
 */
export function AcceptReason({
  chargeId,
  reason,
  onWrite,
  reusesId = null,
  label = "Accept with a note",
}: {
  /** The charge the reason is on; null for a problem on the grant itself, which is always accepted as a one-off. */
  chargeId: Id | null;
  /** The problem being accepted: a charge's reason or a grant's problem. */
  reason: Pick<Problem, "check" | "problem" | "text" | "record_ids">;
  onWrite: OnWrite;
  /** The offered note this acceptance reuses, when the accountant takes an offer by writing the note out. */
  reusesId?: Id | null;
  label?: string;
}) {
  const write = useWrite(onWrite);
  const [note, setNote] = useState("");
  const [reusable, setReusable] = useState(false);
  const [missing, setMissing] = useState(false);
  const id = `accept-${reason.check}-${reason.problem}${reusesId ? "-reuse" : ""}`;
  return (
    <Opener label={label}>
      {(close) => {
        async function submit(event: FormEvent) {
          event.preventDefault();
          if (!note.trim()) return setMissing(true);
          const ok = await write.run({
            data: {
              kind: "accepted_reason",
              // Without a charge, record or file, an acceptance is about the grant itself.
              ...(chargeId ? { charge_id: chargeId } : {}),
              reason: { check: reason.check, problem: reason.problem },
              note: note.trim(),
              reusable: chargeId ? reusable : false,
              ...(reusesId ? { reuses_id: reusesId } : {}),
              rests_on: reason.record_ids ?? [],
            },
          });
          if (ok) close();
        }
        return (
          <form className={styles.form} onSubmit={submit} aria-label={`${label}: ${reason.text}`}>
            <label className="ft-label" htmlFor={id}>
              Note
            </label>
            <textarea id={id} value={note} onChange={(e) => setNote(e.target.value)} />
            {missing && !note.trim() && <p className="ft-error">Write a note.</p>}
            {/* A reusable note is about charges; a grant's own problem is always accepted once. */}
            {chargeId && (
              <fieldset className={styles.choices}>
                <legend className="ft-label">Use the note</legend>
                <label>
                  <input type="radio" name={`${id}-reuse`} checked={!reusable} onChange={() => setReusable(false)} /> Just this charge
                </label>
                <label>
                  <input type="radio" name={`${id}-reuse`} checked={reusable} onChange={() => setReusable(true)} /> This and similar charges
                </label>
              </fieldset>
            )}
            <FormButtons busy={write.busy} submit="Accept" onCancel={close} />
            <Errors errors={write.errors} />
          </form>
        );
      }}
    </Opener>
  );
}

/**
 * The note code offers on a similar charge: one click accepts the same way,
 * for just this charge (the suggested default, which leaves the note's amount
 * limit alone) or for this and similar charges (which raises it). Without the
 * note's text there's nothing to copy, and a note can't be empty, so the
 * accountant writes it out in the accept form, which still reuses the note.
 */
export function OfferedNote({ chargeId, reason, note, onWrite }: { chargeId: Id; reason: Reason; note: FtRecord | null; onWrite: OnWrite }) {
  const write = useWrite(onWrite);
  const text = note ? field<string>(note, "note")?.trim() : undefined;
  const offeredId = reason.offered_note_id ?? null;
  if (!text) {
    return (
      <div className={styles.offer} data-testid="offered-note">
        <p>
          <span className="ft-label">Your earlier note</span> A note you accepted on a similar charge is offered. Its text isn&apos;t on this page.
        </p>
        <AcceptReason chargeId={chargeId} reason={reason} onWrite={onWrite} reusesId={offeredId} label="Accept the same way, with a note" />
      </div>
    );
  }
  const noteText = text;
  async function accept(reusable: boolean) {
    await write.run({
      data: {
        kind: "accepted_reason",
        charge_id: chargeId,
        reason: { check: reason.check, problem: reason.problem },
        note: noteText,
        reusable,
        reuses_id: offeredId,
        rests_on: reason.record_ids ?? [],
      },
    });
  }
  return (
    <div className={styles.offer} data-testid="offered-note">
      <p>
        <span className="ft-label">Your earlier note</span> {noteText}
      </p>
      <p className="ft-caption">Accept this the same way?</p>
      <div className={styles.actions}>
        <button type="button" className="ft-btn ft-btn--sm" disabled={write.busy} onClick={() => void accept(false)}>
          Just this charge
        </button>
        <button type="button" className="ft-btn ft-btn--sm" disabled={write.busy} onClick={() => void accept(true)}>
          This and similar charges
        </button>
      </div>
      <Errors errors={write.errors} />
    </div>
  );
}

/** Reopens an accepted reason: a retraction of the acceptance, which puts the charge back on the list. */
export function ReopenReason({ acceptedId, onWrite }: { acceptedId: Id; onWrite: OnWrite }) {
  const write = useWrite(onWrite);
  return (
    <div className={styles.actions}>
      <button
        type="button"
        className="ft-btn ft-btn--sm"
        disabled={write.busy}
        onClick={() => void write.run({ data: { kind: "retraction", reason: null }, replaces_id: acceptedId })}
      >
        Reopen
      </button>
      <Errors errors={write.errors} />
    </div>
  );
}

// --- Snoozing ---

/**
 * Hides the charge's problems from the list until a date. The charge keeps its
 * bucket. The server enforces the limits, such as the closeout window.
 */
export function SnoozeCharge({ chargeId, reasons, onWrite }: { chargeId: Id; reasons: Reason[]; onWrite: OnWrite }) {
  const write = useWrite(onWrite);
  const [until, setUntil] = useState("");
  const [note, setNote] = useState("");
  const [chosen, setChosen] = useState<string[]>(() => reasons.map((r) => `${r.check}:${r.problem}`));
  const [problem, setProblem] = useState<string | null>(null);
  if (reasons.length === 0) return null;
  return (
    <Opener label="Snooze">
      {(close) => {
        async function submit(event: FormEvent) {
          event.preventDefault();
          if (!until || !note.trim()) return setProblem("Choose a date and write a note.");
          const refs = reasons.filter((r) => chosen.includes(`${r.check}:${r.problem}`)).map((r) => ({ check: r.check, problem: r.problem }));
          if (refs.length === 0) return setProblem("Choose at least one reason.");
          setProblem(null);
          const ok = await write.run({ data: { kind: "snooze", charge_id: chargeId, until, note: note.trim(), reasons: refs } });
          if (ok) close();
        }
        return (
          <form className={styles.form} onSubmit={submit} aria-label="Snooze this charge">
            <label className="ft-label" htmlFor="snooze-until">
              Until
            </label>
            <input id="snooze-until" type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
            <label className="ft-label" htmlFor="snooze-note">
              Note
            </label>
            <textarea id="snooze-note" value={note} onChange={(e) => setNote(e.target.value)} />
            <fieldset className={styles.choices}>
              <legend className="ft-label">Reasons it covers</legend>
              {reasons.map((r) => {
                const key = `${r.check}:${r.problem}`;
                return (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={chosen.includes(key)}
                      onChange={(e) => setChosen((c) => (e.target.checked ? [...c, key] : c.filter((k) => k !== key)))}
                    />{" "}
                    {r.text}
                  </label>
                );
              })}
            </fieldset>
            {problem && <p className="ft-error">{problem}</p>}
            <FormButtons busy={write.busy} submit="Snooze" onCancel={close} />
            <Errors errors={write.errors} />
          </form>
        );
      }}
    </Opener>
  );
}
