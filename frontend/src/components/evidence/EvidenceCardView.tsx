import Link from "next/link";
import type { EvidenceCard, FactView, Id, RecordState, ValueState } from "@/lib/api";
import { date, money, recordKindLabel, SOURCE_LABELS } from "@/lib/format";
import { routes } from "@/lib/routes";
import { pageCaption } from "@/components/viewer/placement";
import styles from "./evidence.module.css";
import { confirmHref, viewerHref } from "./links";
import { confirmationText, displayValue, isCited, valueAt, valueLabel } from "./values";

/** A record's state in a few words, shown only when it isn't simply in force. */
const STATE_WORDS: Partial<Record<RecordState, string>> = {
  waiting: "Waiting for the accountant",
  rejected: "Rejected",
  replaced: "Replaced",
  retracted: "Retracted",
};

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

function ValueRow({ grantId, fact, state }: { grantId: Id; fact: FactView; state: ValueState }) {
  const cited = valueAt(fact.record.data, state.path);
  const label = valueLabel(state.path);
  if (!isCited(cited)) {
    return (
      <>
        <dt>{label}</dt>
        <dd>
          <span className={state.confirmed ? "ft-caption" : styles.unconfirmed}>{confirmationText(state)}</span>
        </dd>
      </>
    );
  }
  const citation = cited.citation ?? null;
  const page = citation ? pageCaption(citation) : null;
  const shown = displayValue(state.path, cited);
  return (
    <>
      <dt>{label}</dt>
      <dd>
        <span className="ft-strong">{shown}</span>
        {citation && (
          <Link
            className={styles.quote}
            href={viewerHref(grantId, citation.file_id, fact.record.id, state.path)}
            aria-label={`Open ${label.toLowerCase()} in the viewer`}
          >
            {citation.passage ?? "A box on the image"}
          </Link>
        )}
        <span className="ft-caption">
          {page && <>{page} · </>}
          <span className={state.confirmed ? undefined : styles.unconfirmed}>{confirmationText(state)}</span>
        </span>
      </dd>
    </>
  );
}

function Fact({ grantId, fileId, fact }: { grantId: Id; fileId: Id; fact: FactView }) {
  const values = fact.values ?? [];
  const unconfirmed = values.filter((v) => !v.confirmed);
  const stateWords = STATE_WORDS[fact.state];
  const problems = fact.status?.problems ?? [];
  return (
    <li className={styles.fact} aria-label={factTitle(fact)}>
      <div className={styles.factHead}>
        <span className="ft-heading">{factTitle(fact)}</span>
        <span className="ft-tag">{fact.record.author === "agent" ? "Agent" : "Accountant"}</span>
        {stateWords && <span className="ft-tag">{stateWords}</span>}
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
          {values.map((v) => (
            <ValueRow key={v.path} grantId={grantId} fact={fact} state={v} />
          ))}
        </dl>
      ) : (
        <p className="ft-caption">No values read from the file.</p>
      )}

      {(fact.links ?? []).length > 0 && (
        <ul className={styles.links} aria-label="Charges it pays for">
          {(fact.links ?? []).map(({ link, charge }) => (
            <li key={link.id} className="ft-caption">
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
 * quote opens the viewer at that spot.
 */
export function EvidenceCardView({ grantId, card }: { grantId: Id; card: EvidenceCard }) {
  const { file } = card;
  const facts = card.facts ?? [];
  const parent = file.parent_id ? card.files?.[file.parent_id] : undefined;
  const exported = file.exported_from ? (EXPORTED_FROM[file.exported_from] ?? file.exported_from) : null;
  const problems = card.status?.problems ?? [];
  const duplicate = card.duplicate;
  const original = duplicate ? card.files?.[(duplicate.mark.data as { original_file_id: Id }).original_file_id] : undefined;

  return (
    <article className={styles.card} aria-label={file.name}>
      <header className={styles.head}>
        <div>
          <Link className="ft-heading ft-link" href={viewerHref(grantId, file.id)}>
            {file.name}
          </Link>
          <div className={`${styles.meta} ft-caption`}>
            <span>{SOURCE_LABELS[file.source] ?? file.source}</span>
            <span>Arrived {date(file.arrived_at)}</span>
            {file.sender && <span>From {file.sender}</span>}
            {file.document_date && <span>Dated {date(file.document_date)}</span>}
            {parent && <span>Attached to {parent.name}</span>}
            {exported && <span>Exported to PDF from {exported}</span>}
          </div>
        </div>
        {duplicate && (
          <span className="ft-tag">
            Copy of {original?.name ?? "another file"}
            {STATE_WORDS[duplicate.state] ? ` · ${STATE_WORDS[duplicate.state]}` : ""}
          </span>
        )}
      </header>

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
        <p className="ft-empty">No facts read from this file yet.</p>
      )}
    </article>
  );
}
