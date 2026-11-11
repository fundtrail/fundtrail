import Link from "next/link";
import type { Citation, EvidenceCard, FactView, Id, RecordState, ValueState } from "@/lib/api";
import { date, money, recordKindLabel, SOURCE_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { pageCaption } from "@/components/viewer/placement";
import styles from "./evidence.module.css";
import { DecideDuplicate } from "./DecideDuplicate";
import { confirmHref, viewerHref } from "./links";
import { unionRanges, valueRanges } from "./quote";
import { QuoteLink } from "./QuoteLink";
import { confirmationText, displayValue, isCited, valueAt, valueLabel } from "./values";

/** A record's state in a few words, shown only when it isn't simply in force. */
export const STATE_WORDS: Partial<Record<RecordState, string>> = {
  waiting: "Waiting for the accountant",
  rejected: "Rejected",
  replaced: "Replaced",
  retracted: "Retracted",
};

/**
 * What the card says about a file that's a copy of another, whole: "Copy of
 * X", with the duplicate mark's state when it isn't simply in force (for
 * example "· Waiting for the accountant" while the suggestion waits). Null
 * when the file isn't marked as a copy.
 */
export function duplicateWords(card: EvidenceCard): string | null {
  const duplicate = card.duplicate;
  if (!duplicate) return null;
  const original = card.files?.[(duplicate.mark.data as { original_file_id: Id }).original_file_id];
  const state = STATE_WORDS[duplicate.state];
  return `Copy of ${original?.name ?? "another file"}${state ? ` · ${state}` : ""}`;
}

/** Google's types for the files Drive exports to PDF (decision 0025). */
const EXPORTED_FROM: Record<string, string> = {
  "application/vnd.google-apps.document": "Google Docs",
  "application/vnd.google-apps.spreadsheet": "Google Sheets",
  "application/vnd.google-apps.presentation": "Google Slides",
};

function factTitle(fact: FactView): string {
  const data = fact.record.data as { kind: string; label?: unknown };
  const kind = recordKindLabel(data.kind);
  return typeof data.label === "string" && data.label ? `${kind}: ${data.label}` : kind;
}

/** The citation of the value at `path`, or null when it has none. */
function citationOf(fact: FactView, path: string): Citation | null {
  const cited = valueAt(fact.record.data, path);
  return isCited(cited) ? (cited.citation ?? null) : null;
}

/** Two citations of the same passage: same file, same place, same text, same match. */
function samePassage(a: Citation | null, b: Citation | null): boolean {
  if (!a || !b || a.passage === null) return false;
  return (
    a.file_id === b.file_id &&
    a.passage === b.passage &&
    a.match === b.match &&
    JSON.stringify(a.location) === JSON.stringify(b.location)
  );
}

/** The values in order, with consecutive values that cite the identical passage grouped. */
function groupValues(fact: FactView, values: ValueState[]): ValueState[][] {
  const groups: ValueState[][] = [];
  for (const v of values) {
    const last = groups[groups.length - 1];
    if (last && samePassage(citationOf(fact, last[0].path), citationOf(fact, v.path))) last.push(v);
    else groups.push([v]);
  }
  return groups;
}

/** Several values that cite one passage: each value, linking to its own spot, then the passage once. */
function SharedPassage({ grantId, fact, group }: { grantId: Id; fact: FactView; group: ValueState[] }) {
  const citation = citationOf(fact, group[0].path) as Citation;
  const labels = group.map((v) => valueLabel(v.path)).join(", ");
  return (
    <>
      {group.map((v) => (
        <ValueRow key={v.path} grantId={grantId} fact={fact} state={v} shared />
      ))}
      <div className={`${styles.valueRow} ${styles.sharedQuote}`}>
        <dt className="ft-sr">The passage for {labels}</dt>
        <dd>
          <QuoteLink
            citation={citation}
            href={viewerHref(grantId, citation.file_id, fact.record.id, group[0].path)}
            ariaLabel={`Open the passage for ${labels.toLowerCase()} in the viewer`}
            ranges={unionRanges(group.map((v) => valueRanges(citationOf(fact, v.path) as Citation)))}
          />
        </dd>
      </div>
    </>
  );
}

/**
 * One value: its label, the value, its quote, then where it is and whether
 * it's confirmed. In a group that shares one passage (`shared`), the value
 * itself links to its spot and the passage shows once under the group.
 */
function ValueRow({ grantId, fact, state, shared = false }: { grantId: Id; fact: FactView; state: ValueState; shared?: boolean }) {
  const cited = valueAt(fact.record.data, state.path);
  const label = valueLabel(state.path);
  if (!isCited(cited)) {
    return (
      <div className={styles.valueRow}>
        <dt>{label}</dt>
        <dd>
          <span className={state.confirmed ? styles.state : styles.unconfirmed}>{confirmationText(state)}</span>
        </dd>
      </div>
    );
  }
  const citation = cited.citation ?? null;
  const page = citation ? pageCaption(citation) : null;
  const shown = displayValue(state.path, cited);
  const href = citation ? viewerHref(grantId, citation.file_id, fact.record.id, state.path) : null;
  const openLabel = `Open ${label.toLowerCase()} in the viewer`;
  return (
    <div className={shared ? `${styles.valueRow} ${styles.valueRowShared}` : styles.valueRow}>
      <dt>{label}</dt>
      <dd>
        {shared && href ? (
          <Link className={`${styles.value} ${styles.valueLink}`} href={href} aria-label={openLabel}>
            {shown}
          </Link>
        ) : (
          <span className={styles.value}>{shown}</span>
        )}
        {citation && href && !shared && <QuoteLink citation={citation} href={href} ariaLabel={openLabel} />}
        <span className={styles.state}>
          {page && <>{page} · </>}
          <span className={state.confirmed ? undefined : styles.unconfirmed}>{confirmationText(state)}</span>
        </span>
      </dd>
    </div>
  );
}

function Fact({ grantId, fileId, fact }: { grantId: Id; fileId: Id; fact: FactView }) {
  const values = fact.values ?? [];
  const unconfirmed = values.filter((v) => !v.confirmed);
  const stateWords = STATE_WORDS[fact.state];
  const problems = fact.status?.problems ?? [];
  return (
    <li className={styles.fact} aria-label={factTitle(fact)}>
      <div className={fact.state === "waiting" ? `${styles.factHead} ${styles.factHeadWaiting}` : styles.factHead}>
        <span className={styles.factTitle}>{factTitle(fact)}</span>
        <span className="ft-tag">{fact.record.author === "agent" ? "Agent" : "Accountant"}</span>
        {stateWords && <span className={fact.state === "waiting" ? styles.waitingTag : "ft-tag"}>{stateWords}</span>}
      </div>

      {problems.length > 0 && (
        <ul className={styles.problems} aria-label="Problems with this fact">
          {problems.map((p) => (
            <li key={`${p.check}:${p.problem}`}>{p.text}</li>
          ))}
        </ul>
      )}

      {values.length > 0 ? (
        <dl className={styles.values}>
          {groupValues(fact, values).map((group) =>
            group.length > 1 ? (
              <SharedPassage key={group[0].path} grantId={grantId} fact={fact} group={group} />
            ) : (
              <ValueRow key={group[0].path} grantId={grantId} fact={fact} state={group[0]} />
            ),
          )}
        </dl>
      ) : (
        <p className={styles.noValues}>No values read from the file.</p>
      )}

      {(fact.links ?? []).length > 0 && (
        <ul className={styles.links} aria-label="Charges it pays for">
          {(fact.links ?? []).map(({ link, charge }) => (
            <li key={link.id}>
              Linked to{" "}
              <Link className="ft-link" href={routes.charge(grantId, charge.id)}>
                {charge.ledger_line_id} · {charge.description} · {money(charge.amount_cents)}
              </Link>
              {link.data.amount_cents != null && <> · uses {money(link.data.amount_cents)}</>}
              {link.data.part && (
                <>
                  {" · "}
                  <Link className="ft-link" href={viewerHref(grantId, link.data.part.file_id, link.id, "part")}>
                    the part for this charge
                  </Link>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {unconfirmed.length > 0 && (
        <div className={styles.actions}>
          <Link className="ft-btn ft-btn--sm" href={confirmHref(grantId, fileId, fact.record.id)}>
            Confirm or correct {unconfirmed.length === 1 ? "the unconfirmed value" : `${unconfirmed.length} unconfirmed values`}
          </Link>
        </div>
      )}
    </li>
  );
}

/**
 * One file and every fact read from it (product.md, Evidence cards). Each value
 * shows its quoted passage, its page, and whether it's confirmed. Clicking a
 * quote opens the viewer at that spot. While the agent's duplicate mark on the
 * file waits for the accountant, the card offers Confirm and Reject for it.
 */
export function EvidenceCardView({
  grantId,
  card,
  headingLevel,
}: {
  grantId: Id;
  card: EvidenceCard;
  /** Sets the file's name as a heading of this level, for a page where the card is the main item. None by default. */
  headingLevel?: 2 | 3;
}) {
  const { file } = card;
  const facts = card.facts ?? [];
  const parent = file.parent_id ? card.files?.[file.parent_id] : undefined;
  const exported = file.exported_from ? (EXPORTED_FROM[file.exported_from] ?? file.exported_from) : null;
  const problems = card.status?.problems ?? [];
  const copy = duplicateWords(card);
  const name = (
    <Link className={styles.fileName} href={viewerHref(grantId, file.id)}>
      {file.name}
    </Link>
  );
  const Heading = headingLevel ? (`h${headingLevel}` as const) : null;

  return (
    <article className={styles.card} aria-label={file.name}>
      <header className={styles.head}>
        <div>
          {Heading ? <Heading className={styles.fileHeading}>{name}</Heading> : name}
          <div className={styles.meta}>
            <span>{SOURCE_LABELS[file.source] ?? file.source}</span>
            <span>Arrived {date(file.arrived_at)}</span>
            {file.sender && <span>From {file.sender}</span>}
            {file.document_date && <span>Dated {date(file.document_date)}</span>}
            {parent && <span>Attached to {parent.name}</span>}
            {exported && <span>Exported to PDF from {exported}</span>}
          </div>
        </div>
        {copy && <span className="ft-tag">{copy}</span>}
      </header>

      {card.duplicate?.state === "waiting" && <DecideDuplicate grantId={grantId} duplicate={card.duplicate} />}

      {problems.length > 0 && (
        <ul className={styles.problems} aria-label="Problems with this file">
          {problems.map((p) => (
            <li key={`${p.check}:${p.problem}`}>{p.text}</li>
          ))}
        </ul>
      )}

      {facts.length > 0 ? (
        <ul className={styles.facts}>
          {facts.map((f) => (
            <Fact key={f.record.id} grantId={grantId} fileId={file.id} fact={f} />
          ))}
        </ul>
      ) : (
        <p className={styles.noFacts}>No facts read from this file yet.</p>
      )}
    </article>
  );
}
