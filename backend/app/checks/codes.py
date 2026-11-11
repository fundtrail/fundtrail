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
from app.contracts.records import Judgment, Record

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
    """A keyed code's family ("unsure" for "unsure:r15"); any other code as it is."""
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


def flag_code(view: GrantView, r: Record, taken: set[str]) -> str:
    """An agent flag's code: "flag:{rule}", or its root when it names no rule. A second
    current flag with the same rule on the same subject adds its own root, so each one
    has its own code (issue 307)."""
    j = r.data
    assert isinstance(j, Judgment)
    code = f"flag:{j.rule or view.root(r.id)}"
    if code in taken:
        code = f"{code}:{view.root(r.id)}"
    taken.add(code)
    return code
