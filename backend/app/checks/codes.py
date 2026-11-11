"""Reason codes keyed by the record they're about (issue 307).

Several reasons on one subject used to share one check:problem code, so the screens
couldn't tell them apart. The codes below now end with the root of the record they're
about after a colon, for example "unsure:{root}" or "approver_unknown:{root}". A code's
family is the part before that key.

- A stored acceptance or snooze names one reason by its exact code. One stored before
  issue 307, with a family and no key, still names the reasons of that family.
- A reusable note is written on one charge and covers later charges, whose reasons are
  about other records, so it matches by family.
"""

from app.checks.view import GrantView
from app.contracts.records import Judgment, Question, Record

# The keyed families, by check. None means every code of the check is keyed.
KEYED: dict[str, frozenset[str] | None] = {
    "covers": None,
    "unusual_term": None,
    "approval": frozenset(
        {
            "approver_unknown",
            "wrong_approver",
            "email_approval",
            "channel_unknown",
            "wrong_channel",
            "approval_date_unknown",
            "approval_late",
            "not_an_approval",
        }
    ),
    "values_confirmed": frozenset({"term_not_confirmed", "unconfirmed"}),
    "checklist": frozenset({"bill_over_linked"}),
}


def family(check: str, problem: str) -> str:
    """A keyed code's family ("unsure" for "unsure:r15"; "flag:refund" for a second refund
    flag's "flag:refund:r16"); any other code as it is."""
    if check == "flag":
        return ":".join(problem.split(":")[:2])
    if check not in KEYED:
        return problem
    base = problem.partition(":")[0]
    bases = KEYED[check]
    return base if bases is None or base in bases else problem


def same_code(check: str, problem: str, found_check: str, found_problem: str) -> bool:
    """Whether a stored acceptance's or snooze's code names a reason the checks give now:
    the same code, or, for a code stored before issue 307, its family."""
    if check != found_check:
        return False
    if problem == found_problem:
        return True
    return ":" not in problem and family(found_check, found_problem) == problem


def same_family(check: str, problem: str, found_check: str, found_problem: str) -> bool:
    """Whether a reusable note's code covers a reason on a later charge: the same code,
    or for a keyed code the same family (the later reason is about another record)."""
    if check != found_check:
        return False
    return problem == found_problem or family(check, problem) == family(found_check, found_problem)


def _flag_subject(view: GrantView, j: Judgment) -> tuple[str | None, str | None, str | None]:
    record = view.root(j.record_id) if j.record_id is not None else None
    return (j.charge_id, record, j.file_id)


def flag_code(view: GrantView, r: Record) -> str:
    """An agent flag's code: "flag:{rule}", or "flag:{root}" when it names no rule.

    Several flags with one rule on one subject get their own codes (issue 307), and no
    flag's code ever changes: the one whose root was stored first among every flag with
    that rule ever written on the subject (answered, replaced and retracted ones included)
    keeps "flag:{rule}", and every other one is always "flag:{rule}:{root}".
    """
    j = r.data
    assert isinstance(j, Judgment)
    root = view.root(r.id)
    # The rule the flag was raised under: an answer replacing it may not repeat it.
    first_written = view.state.by_id.get(root)
    rule = j.rule or (
        first_written.data.rule
        if first_written is not None and isinstance(first_written.data, Judgment)
        else None
    )
    if not rule:
        return f"flag:{root}"
    subject = _flag_subject(view, j)
    first = next(
        (
            view.root(x.id)
            for x in view.state.records
            if isinstance(x.data, Judgment)
            and x.data.question == Question.FLAG
            and x.data.rule == rule
            and _flag_subject(view, x.data) == subject
        ),
        root,
    )
    return f"flag:{rule}" if first == root else f"flag:{rule}:{root}"
