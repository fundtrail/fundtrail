import Link from "next/link";
import type { GrantSummary, Id, ReadingProgress } from "@/lib/api";
import { routes } from "@/lib/routes";
import styles from "./AgentProgress.module.css";

/**
 * Whether the agent is reading the grant now. Ruling 71: the server sends
 * `reading` only while the grant has runs queued or running that cover files or
 * ledger lines, and null otherwise, so its presence is the answer. The screen
 * adds no rule of its own.
 */
export function readingNow(summary: GrantSummary): ReadingProgress | null {
  return summary.reading ?? null;
}

/** "3 of 8 files", or "1 of 1 file": the server's two numbers, as given. */
function countWords(read: number, total: number, one: string, many: string): string {
  return `${read} of ${total} ${total === 1 ? one : many}`;
}

/** The parts of the server's counts worth saying: files and ledger lines, each only when its total is above zero. */
function readingParts(reading: ReadingProgress): string[] {
  const parts: string[] = [];
  if (reading.files_total > 0) parts.push(countWords(reading.files_read, reading.files_total, "file", "files"));
  if (reading.lines_total > 0) parts.push(countWords(reading.lines_read, reading.lines_total, "ledger line", "ledger lines"));
  return parts;
}

/** A small dot that pulses while the agent works; still under reduced motion. */
export function WorkingDot() {
  return <span className={styles.dot} aria-hidden="true" />;
}

/**
 * The grant overview's quiet line about the agent's work: while it reads files
 * or ledger lines, how far it is, in the server's numbers ("The agent is
 * reading: 3 of 8 files, 12 of 40 ledger lines."); otherwise, including runs
 * that cover no file or ledger line, the last run's summary in the server's
 * words, muted; otherwise nothing. The status region stays in place, so a
 * change is announced politely and a refetch with the same numbers changes
 * nothing.
 */
export function AgentProgressLine({ summary }: { summary: GrantSummary }) {
  const reading = readingNow(summary);
  const parts = reading ? readingParts(reading) : [];
  const last = summary.last_run_summary?.trim() || null;
  return (
    <div role="status" className={styles.region}>
      {parts.length > 0 ? (
        <p className={styles.line}>
          <WorkingDot />
          <span>The agent is reading: {parts.join(", ")}.</span>
        </p>
      ) : (
        last && (
          <p className={`${styles.line} ${styles.last}`}>
            <span>{last}</span>
          </p>
        )
      )}
    </div>
  );
}

/**
 * The top bar's working indicator for the grant the page is inside, while the
 * agent reads its files or ledger lines: the dot and a short count, linking to
 * the grant's overview. Its accessible name starts with what it shows and
 * carries the full counts; so does its title.
 */
export function WorkingIndicator({ grantId, summary }: { grantId: Id; summary: GrantSummary }) {
  const reading = readingNow(summary);
  const parts = reading ? readingParts(reading) : [];
  if (parts.length === 0) return null;
  return (
    <Link
      className={styles.indicator}
      href={routes.grant(grantId)}
      title={`The agent is reading: ${parts.join(", ")}.`}
      aria-label={`Reading ${parts.join(", ")}. Open the grant's overview.`}
    >
      <WorkingDot />
      <span>Reading {parts[0]}</span>
    </Link>
  );
}
