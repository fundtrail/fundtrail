import type { AnswerView, Citation, EvidenceFile, Id, OpenQuestion } from "@/lib/api";
import { date } from "@/lib/format";
import { Quote } from "../thread/Decide";
import type { OnWrite } from "../thread/useThreadActions";
import { AnswerOpenQuestion, OverruleAnswer } from "./actions";
import { ANSWER_LABELS, field, QUESTION_LABELS } from "./labels";
import { TrailGroup, TrailNode, TrailNote, type Mark } from "./Trail";
import styles from "./charge.module.css";

const ANSWER_MARKS: Record<string, Mark> = { supports: "holds", contradicts: "conflict", unsure: "human" };

/**
 * The answers to the questions code asked about the charge, as nodes on the
 * evidence trail: the question, the answer, the reasoning, the rule it used
 * and its quotes, labeled with who wrote it. Then the questions still open,
 * and who answers each. A Supports answer is a single line that opens in
 * place; Contradicts and Unsure show their detail. With `onWrite`, the
 * accountant answers any open question, including one waiting for the agent,
 * or overrules an answer.
 */
export function AgentAnswers({
  answers,
  questions,
  rechecking,
  files,
  quoteHref,
  chargeId,
  onWrite,
}: {
  answers: AnswerView[];
  questions: OpenQuestion[];
  rechecking: boolean;
  files: Record<Id, EvidenceFile>;
  quoteHref?: (citation: Citation) => string | undefined;
  chargeId?: Id;
  onWrite?: OnWrite;
}) {
  if (answers.length === 0 && questions.length === 0) {
    return (
      <TrailGroup label="Answers">
        <TrailNote>No questions about this charge yet.</TrailNote>
      </TrailGroup>
    );
  }
  return (
    <TrailGroup label="Answers">
      {answers.map(({ judgment, out_of_date, rule }) => {
        const answer = field<string>(judgment, "answer") ?? "";
        const quotes = field<Citation[]>(judgment, "quotes") ?? [];
        const byAgent = judgment.author === "agent";
        const settled = answer === "supports";
        return (
          <TrailNode
            key={judgment.id}
            testId="answer"
            mark={ANSWER_MARKS[answer] ?? "plain"}
            broken={!settled}
            open={!settled}
            title={<span className={styles.label}>{field<string>(judgment, "text")}</span>}
            status={
              <>
                {out_of_date && <span className="ft-tag">Out of date</span>}
                {out_of_date && rechecking && <span className="ft-tag ft-tag--rechecking">Rechecking</span>}
                <span className="ft-tag">{byAgent ? "Agent" : "Accountant"}</span>
                <span className={styles.answer} data-answer={answer}>
                  {ANSWER_LABELS[answer] ?? answer}
                </span>
              </>
            }
          >
            <p className="ft-caption">
              {byAgent ? "The agent's answer" : "Answered by the accountant"}, {date(judgment.written_at)}
            </p>
            <p className={styles.prose}>
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
              <Quote key={i} citation={q} files={files} href={quoteHref?.(q)} highlight={!settled} />
            ))}
            {onWrite && <OverruleAnswer judgment={judgment} onWrite={onWrite} />}
          </TrailNode>
        );
      })}
      {questions.map((q, i) => (
        <TrailNode
          key={`q:${q.question}:${q.record_id ?? i}`}
          testId="open-question"
          mark={q.answer_by === "agent" ? "plain" : "human"}
          broken
          open
          title={
            <>
              <span className="ft-tag">Open question</span> <span className={styles.label}>{QUESTION_LABELS[q.question] ?? q.question}</span>
            </>
          }
          status={q.answer_by === "agent" ? "Waiting for the agent" : "Waiting for the accountant"}
        >
          {onWrite ? <AnswerOpenQuestion chargeId={chargeId ?? q.charge_id} question={q} onWrite={onWrite} /> : null}
        </TrailNode>
      ))}
    </TrailGroup>
  );
}
