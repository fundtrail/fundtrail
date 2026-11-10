"""The questions code asks about a charge, and the answers in force (contracts.md section 4).

- An answer is out of date when a link to its charge was written after it, or a
  record it rests on (or the record it's about) is no longer current.
- The agent's out-of-date answer keeps the charge's bucket, marked rechecking,
  and the question is open for the agent. The accountant's out-of-date answer
  goes back to the accountant, and the charge is in Needs a human meanwhile.
- No current answer: Needs a human, and the question is open.
- Several current answers to one question (whether a question has one answer
  in force isn't settled in the contracts): the latest current answer counts.
"""

from dataclasses import dataclass

from app.checks.findings import Finding
from app.checks.view import GrantView
from app.contracts.checks import Bucket, OpenQuestion
from app.contracts.records import Answer, Author, Judgment, Link, Question, Record

ANSWER_BUCKET = {
    Answer.SUPPORTS: Bucket.EVIDENCE_COMPLETE,
    Answer.CONTRADICTS: Bucket.POSSIBLE_CONFLICT,
    Answer.UNSURE: Bucket.NEEDS_HUMAN,
}


@dataclass
class AnswerState:
    question: Question
    record_id: str | None
    label: str
    judgment: Record | None
    out_of_date: bool
    answer_by: Author  # who answers it next, when it's open

    @property
    def answer(self) -> Answer | None:
        if self.judgment is None:
            return None
        assert isinstance(self.judgment.data, Judgment)
        return self.judgment.data.answer

    @property
    def by_user(self) -> bool:
        return self.judgment is not None and self.judgment.author == Author.USER

    @property
    def is_open(self) -> bool:
        return self.judgment is None or self.out_of_date

    @property
    def rechecking(self) -> bool:
        return self.judgment is not None and self.out_of_date and not self.by_user

    def counts_as(self, answer: Answer) -> bool:
        """Whether the bucket uses this answer. The accountant's out-of-date answer isn't used."""
        return self.answer == answer and not (self.by_user and self.out_of_date)

    def finding(self) -> Finding:
        check = self.question.value
        if self.judgment is None:
            return Finding(
                check, "not_answered", Bucket.NEEDS_HUMAN, f"{self.label}: not answered yet."
            )
        j = self.judgment.data
        assert isinstance(j, Judgment)
        ids = [self.judgment.id, *j.rests_on]
        if self.by_user and self.out_of_date:
            return Finding(
                check,
                "out_of_date",
                Bucket.NEEDS_HUMAN,
                f"{self.label}: the accountant's answer is out of date, so it's back with the "
                "accountant.",
                ids,
            )
        who = "The accountant" if self.by_user else "The agent"
        text = f"{self.label}: {who} answered {j.answer.value}."
        if self.rechecking:
            text += " Something changed since, and the agent is answering again."
        return Finding(check, j.answer.value, ANSWER_BUCKET[j.answer], text, ids)

    def open_question(self, charge_id: str) -> OpenQuestion:
        return OpenQuestion(
            charge_id=charge_id,
            question=self.question,
            record_id=self.record_id,
            answer_by=self.answer_by,
        )


def _out_of_date(view: GrantView, judgment: Record) -> bool:
    j = judgment.data
    assert isinstance(j, Judgment)
    at = view.pos[judgment.id]
    for r in view.current:
        if isinstance(r.data, Link) and r.data.charge_id == j.charge_id and view.pos[r.id] > at:
            return True
    rests = list(j.rests_on) + ([j.record_id] if j.record_id else [])
    return any(not view.state.is_current(rid) for rid in rests)


def answer_state(
    view: GrantView, charge_id: str, question: Question, record_id: str | None, label: str
) -> AnswerState:
    found = view.judgments_for(charge_id, question, record_id)
    chosen: Record | None = found[-1] if found else None  # records come in the order written
    user_before = view.ever_answered_by_user(charge_id, question, record_id)
    return AnswerState(
        question=question,
        record_id=record_id,
        label=label,
        judgment=chosen,
        out_of_date=chosen is not None and _out_of_date(view, chosen),
        answer_by=Author.USER if user_before else Author.AGENT,
    )
