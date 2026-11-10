import type { AnswerView, Citation, EvidenceFile, Id, OpenQuestion } from "@/lib/api";
import { date } from "@/lib/format";
import { Quote } from "../thread/Decide";
import { ANSWER_LABELS, field, QUESTION_LABELS } from "./labels";
import styles from "./charge.module.css";

/**
 * The answers to the questions code asked about the charge: the question, the
 * answer, the reasoning, the rule it used and its quotes, labeled with who
 * wrote it. Then the questions still open, and who answers each.
 */
export function AgentAnswers({
  answers,
  questions,
  rechecking,
  files,
  quoteHref,
}: {
  answers: AnswerView[];
  questions: OpenQuestion[];
  rechecking: boolean;
  files: Record<Id, EvidenceFile>;
  quoteHref?: (citation: Citation) => string | undefined;
}) {
  if (answers.length === 0 && questions.length === 0) {
    return <p className="ft-empty">No questions about this charge yet.</p>;
  }
  return (
    <ul className={styles.list} aria-label="Answers">
      {answers.map(({ judgment, out_of_date, rule }) => {
        const answer = field<string>(judgment, "answer") ?? "";
        const quotes = field<Citation[]>(judgment, "quotes") ?? [];
        const byAgent = judgment.author === "agent";
        return (
          <li key={judgment.id} className={styles.row} data-testid="answer">
            <p className={styles.line}>
              <span className="ft-tag">{byAgent ? "Agent" : "Accountant"}</span>
              <span className={styles.label}>{field<string>(judgment, "text")}</span>
            </p>
            <p className={styles.line}>
              <span className={styles.answer} data-answer={answer}>
                {ANSWER_LABELS[answer] ?? answer}
              </span>
              <span className="ft-caption">
                {byAgent ? "The agent's answer" : "Answered by the accountant"}, {date(judgment.written_at)}
              </span>
              {out_of_date && <span className="ft-tag">Out of date</span>}
              {out_of_date && rechecking && <span className="ft-tag ft-tag--rechecking">Rechecking</span>}
            </p>
            <p>
              <span className="ft-label">{byAgent ? "Agent's reasoning" : "Accountant's reasoning"}</span>{" "}
              {field<string>(judgment, "reasoning")}
            </p>
            {rule && (
              <div className={styles.rule}>
                <p>
                  <span className="ft-label">Rule</span> <span className="ft-id">{rule.id}</span> {rule.title}
                </p>
                <p className="ft-caption">{rule.text}</p>
                {(rule.sources ?? []).length > 0 && (
                  <p className="ft-caption">
                    {(rule.sources ?? []).map((s, i) => (
                      <span key={s.url}>
                        {i > 0 && " · "}
                        <a className="ft-link" href={s.url} target="_blank" rel="noreferrer">
                          {s.label}
                        </a>
                      </span>
                    ))}
                  </p>
                )}
              </div>
            )}
            {!rule && field<string | null>(judgment, "rule") && (
              <p className="ft-caption">
                Rule <span className="ft-id">{field<string>(judgment, "rule")}</span>
              </p>
            )}
            {quotes.map((q, i) => (
              <Quote key={i} citation={q} files={files} href={quoteHref?.(q)} />
            ))}
          </li>
        );
      })}
      {questions.map((q, i) => (
        <li key={`q:${q.question}:${q.record_id ?? i}`} className={styles.row} data-testid="open-question">
          <p className={styles.line}>
            <span className="ft-tag">Open question</span>
            <span className={styles.label}>{QUESTION_LABELS[q.question] ?? q.question}</span>
          </p>
          <p className="ft-caption">{q.answer_by === "agent" ? "Waiting for the agent" : "Waiting for the accountant"}</p>
        </li>
      ))}
    </ul>
  );
}
