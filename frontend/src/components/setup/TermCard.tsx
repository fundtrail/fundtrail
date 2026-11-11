"use client";

import Link from "next/link";
import { useId, useState, type ReactNode } from "react";
import { viewerHref } from "@/components/evidence/links";
import { pageCaption } from "@/components/viewer/placement";
import type { Citation, FtRecord, RecordData, RecordDataInput, RecordState, TermView } from "@/lib/api";
import { date, recordKindLabel } from "@/lib/format";
import { routes } from "@/lib/routes";
import { isTermKind, readField, showValue, TERM_FIELDS, TERM_KIND_LABELS, type TermField, type TermKind } from "./termFields";
import { TermQuote, valueSpans, type Span } from "./TermQuote";
import { TypeTermForm } from "./TypeTermForm";
import { useWrite, WriteProblems } from "./useWrite";
import "./setup.css";

const STATE_LABELS: Record<RecordState, string> = {
  counts: "In force",
  waiting: "Waiting for you",
  rejected: "Rejected",
  replaced: "Replaced",
  retracted: "Withdrawn",
};

function decisionWord(data: RecordData): string {
  if (data.kind === "confirmation") return data.decision === "rejected" ? "Rejected" : "Confirmed";
  return recordKindLabel(data.kind);
}

const SAVED_LABELS = { confirmed: "Confirmed.", rejected: "Rejected.", typed: "Your value is saved." } as const;

/** A field's value as the screen shows it, or "" when the term doesn't state it. */
function shownValue(record: FtRecord, kind: TermKind, path: string): string {
  const field = TERM_FIELDS[kind].find((f) => f.path === path);
  return field ? showValue(field.type, readField(record, field).value) : "";
}

/** Short label and value pairs, for the kinds whose summary is a list. */
function Pairs({ pairs }: { pairs: [string, string][] }) {
  return (
    <span className="ft-ts__pairs">
      {pairs
        .filter(([, value]) => value !== "")
        .map(([label, value]) => (
          <span key={label} className="ft-ts__pair">
            <span className="ft-ts__label">{label}</span> {value}
          </span>
        ))}
    </span>
  );
}

/**
 * A term's values in one line, laid out for its kind: what the closed row
 * shows. The values only, in ink; their quotes and who wrote them are inside.
 */
function termSummary({ record, kind }: { record: FtRecord; kind: TermKind }): { main: ReactNode; aside?: ReactNode } {
  const v = (path: string) => shownValue(record, kind, path);
  switch (kind) {
    case "period_of_performance": {
      const start = v("start");
      const end = v("end");
      if (start && end) return { main: <span className="ft-ts__strong">{`${start} to ${end}`}</span> };
      return { main: <Pairs pairs={[["Start date", start], ["End date", end || "Not stated"]]} /> };
    }
    case "budget_line":
      return {
        main: <span className="ft-ts__strong">{v("name") || "Not stated"}</span>,
        aside: <span className="ft-ts__amount">{v("amount") || "Not stated"}</span>,
      };
    case "rate":
      return {
        main: <span className="ft-ts__strong">{v("name") || "Not stated"}</span>,
        aside: <span className="ft-ts__amount">{v("rate") || "Not stated"}</span>,
      };
    case "person":
      return {
        main: (
          <span className="ft-ts__line">
            <span className="ft-ts__strong">{v("name") || "Not stated"}</span>
            {[v("role"), v("email")]
              .filter((x) => x !== "")
              .map((x) => (
                <span key={x}>{x}</span>
              ))}
          </span>
        ),
      };
    case "approval_rule":
      return {
        main: (
          <Pairs
            pairs={[
              ["Applies to", v("applies_to") || "Not stated"],
              ["Approver", v("approver") || "Not stated"],
              ["How", v("channel")],
              ["Scope", v("scope")],
            ]}
          />
        ),
      };
    case "notice":
      return {
        main: (
          <Pairs
            pairs={[
              ["Amendment", v("amendment_number") || "Not stated"],
              ["Type", v("amendment_type") || "Not stated"],
              ["This amendment", v("obligated_by_amendment")],
              ["To date", v("obligated_to_date")],
            ]}
          />
        ),
      };
    case "other_term":
      return {
        main: (
          <span className="ft-ts__line ft-ts__line--clip">
            <span className="ft-ts__strong">{v("label") || "Not stated"}</span>
            <span>{v("statement")}</span>
          </span>
        ),
      };
  }
}

/** One value of a term as the open row lists it. */
interface ShownField {
  field: TermField;
  shown: string;
  text: string | null;
  citation: Citation | null;
}

/** Where a citation points, so consecutive values that quote the same words in the same place show them once. */
function passageKey(c: Citation | null): string | null {
  if (!c || c.passage === null) return null;
  return `${c.file_id}|${JSON.stringify(c.location)}|${c.passage}`;
}

/** The values in order, consecutive ones that cite the identical passage together. */
function groupByPassage(fields: ShownField[]): ShownField[][] {
  const groups: ShownField[][] = [];
  for (const f of fields) {
    const last = groups[groups.length - 1];
    const key = passageKey(f.citation);
    if (last && key !== null && passageKey(last[0]!.citation) === key) last.push(f);
    else groups.push([f]);
  }
  return groups;
}

/** Every value's own characters in a passage they share. */
function sharedSpans(group: ShownField[]): Span[] | null {
  const spans = group.flatMap((f) => (f.citation ? (valueSpans(f.citation) ?? []) : []));
  return spans.length > 0 ? spans.sort((a, b) => a.start - b.start) : null;
}

/**
 * One grant term as one row. Closed, the row shows the term's values plainly,
 * and a tag only when its state isn't the ordinary one. Opened, it shows each
 * value with its quote and a link to its spot in the file, who read and
 * confirmed it and when, its thread, and, while it waits, Confirm, Reject and
 * Type the right value. It opens by itself when it needs the accountant: it
 * waits, a value couldn't be found in the file, or the term has a problem.
 */
export function TermCard({ term, settled = false }: { term: TermView; settled?: boolean }) {
  const { record } = term;
  const kind = record.data.kind;
  const detailId = useId();
  const { state, write } = useWrite();
  const [typing, setTyping] = useState(false);
  const [done, setDone] = useState<keyof typeof SAVED_LABELS | null>(null);
  const unconfirmed = (term.values ?? []).filter((v) => !v.confirmed);
  const problems = term.status?.problems ?? [];
  const waiting = term.state === "waiting";
  const [open, setOpen] = useState(waiting || unconfirmed.length > 0 || problems.length > 0);

  if (!isTermKind(kind)) return null;
  const fields = TERM_FIELDS[kind];
  const fieldLabel = (path: string) => fields.find((f) => f.path === path)?.label ?? path.replaceAll("_", " ");
  const saving = state.status === "saving";
  // A wrong term is rejected, then fixed by typing the right value (product.md, Grants).
  const rejectedNow = done === "rejected" || (done === null && term.state === "rejected");
  const fixable = record.author === "agent" && rejectedNow;

  async function decide(decision: "confirmed" | "rejected") {
    const saved = await write(record.grant_id, { data: { kind: "confirmation", record_ids: [record.id], decision } });
    if (saved) setDone(decision);
  }

  async function saveTyped(data: RecordDataInput) {
    const saved = await write(record.grant_id, { data, replaces_id: record.id });
    if (saved) {
      setTyping(false);
      setDone("typed");
    }
  }

  const muted = term.state === "rejected" || term.state === "replaced" || term.state === "retracted";
  const deciding = waiting && !typing && done === null && !settled;
  const offerTyping = fixable && !typing;
  const summary = termSummary({ record, kind });
  const shownFields: ShownField[] = fields.flatMap((field) => {
    const { value, text, citation } = readField(record, field);
    const shown = showValue(field.type, value);
    if (!shown && field.optional) return [];
    return [{ field, shown, text, citation }];
  });

  return (
    <article className={`ft-trow${open ? " is-open" : ""}${muted ? " is-muted" : ""}`} aria-label={`${TERM_KIND_LABELS[kind]} term`}>
      <button type="button" className="ft-trow__head" aria-expanded={open} aria-controls={detailId} onClick={() => setOpen((o) => !o)}>
        <span className="ft-trow__chev" aria-hidden="true" />
        <span className={`ft-trow__main${muted ? " ft-struck" : ""}`}>{summary.main}</span>
        {summary.aside && <span className={`ft-trow__aside${muted ? " ft-struck" : ""}`}>{summary.aside}</span>}
        <span className="ft-trow__tags">
          {term.state !== "counts" && <span className={`ft-tag${waiting ? " ft-tag--waiting" : ""}`}>{STATE_LABELS[term.state]}</span>}
          {unconfirmed.length > 0 && <span className="ft-tag ft-tag--waiting">Unconfirmed</span>}
        </span>
      </button>

      {open && (
        <div id={detailId} className="ft-trow__detail">
          <div className="ft-trow__body">
            <div className="ft-tvals">
              {groupByPassage(shownFields).map((group) => {
                const citation = group[0]!.citation;
                return (
                  <div key={group[0]!.field.path} className="ft-tvals__group">
                    {group.map(({ field, shown, text, citation: c }) => {
                      const page = c ? pageCaption(c) : null;
                      return (
                        <div key={field.path} className="ft-tval">
                          <span className="ft-label">{field.label}</span>
                          <span className={`ft-tval__value${muted ? " ft-struck" : ""}`}>
                            {shown || "Not stated"}
                            {!c && text && <span className="ft-caption"> · written “{text}”</span>}
                          </span>
                          {c && (
                            <span className="ft-tval__src">
                              {page && <>{page} · </>}
                              <Link
                                className="ft-link"
                                href={viewerHref(record.grant_id, c.file_id, record.id, field.path)}
                                aria-label={`Open the source of ${field.label.toLowerCase()}`}
                              >
                                Open the source
                              </Link>
                            </span>
                          )}
                        </div>
                      );
                    })}
                    {citation?.passage && (
                      <TermQuote citation={{ ...citation, passage: citation.passage }} spans={sharedSpans(group)} />
                    )}
                  </div>
                );
              })}
            </div>

            {unconfirmed.length > 0 && (
              <div className="ft-trow__unconfirmed">
                <p className="ft-label">Couldn&apos;t be found in the file</p>
                <ul aria-label="Values not confirmed">
                  {unconfirmed.map((v) => (
                    <li key={v.path}>{fieldLabel(v.path)}</li>
                  ))}
                </ul>
              </div>
            )}

            {problems.map((p) => (
              <p key={`${p.check}:${p.problem}`} className="ft-problem__text">
                {p.text}
              </p>
            ))}

            <p className="ft-caption ft-trow__who">
              <span>
                {record.author === "agent" ? "Read by the agent" : "Typed by the accountant"}, <span className="ft-nowrap">{date(record.written_at)}</span>
              </span>
              {term.decision && !waiting && (
                <span>
                  {decisionWord(term.decision.data)} by the accountant, <span className="ft-nowrap">{date(term.decision.written_at)}</span>
                </span>
              )}
            </p>
            <p className="ft-caption">
              <Link className="ft-link" href={routes.record(record.grant_id, record.id)}>
                Open the term&apos;s thread
              </Link>
              {record.author === "agent" && " to tell the agent where to look"}
            </p>
            <WriteProblems state={state} />
          </div>

          {(deciding || offerTyping || done) && (
            <div className="ft-trow__actions">
              {done && (
                <p className="ft-trow__done" role="status">
                  {SAVED_LABELS[done]}
                </p>
              )}
              {deciding && (
                <>
                  <button type="button" className="ft-btn ft-btn--sm ft-btn--approve" disabled={saving} onClick={() => void decide("confirmed")}>
                    Confirm
                  </button>
                  <button type="button" className="ft-btn ft-btn--sm ft-btn--reject" disabled={saving} onClick={() => void decide("rejected")}>
                    Reject
                  </button>
                  <button type="button" className="ft-btn ft-btn--sm ft-btn--quiet" disabled={saving} onClick={() => setTyping(true)}>
                    Type the right value
                  </button>
                </>
              )}
              {offerTyping && (
                <button type="button" className="ft-btn ft-btn--sm ft-btn--quiet" disabled={saving} onClick={() => setTyping(true)}>
                  Type the right value
                </button>
              )}
            </div>
          )}

          {typing && (
            <div className="ft-trow__form">
              <TypeTermForm term={record} kind={kind} saving={saving} onSave={(d) => void saveTyped(d)} onCancel={() => setTyping(false)} />
            </div>
          )}
        </div>
      )}
    </article>
  );
}
