"""Issue 104: a budget line names the notice it belongs to."""

from typing import Any

from app.contracts import api
from app.contracts.records import BudgetLine
from tests.contracts.factory import FILES, agent, budget_line, file, problems, user


def typed_line(**changes: Any) -> dict[str, Any]:
    line = budget_line()
    del line["dated"]  # the server fills it for the accountant's term
    return line | changes


def test_the_accountant_types_a_line_with_its_notice():
    body = api.NewRecordInput.model_validate({"data": typed_line(notice_file_id="f3")})
    assert isinstance(body.data, BudgetLine) and body.data.notice_file_id == "f3"
    assert api.NewRecordInput.model_validate({"data": typed_line()}).data.notice_file_id is None  # pyright: ignore[reportAttributeAccessIssue]


def test_the_notice_is_an_evidence_file_on_the_lines_grant():
    assert problems(user("t1", budget_line() | {"notice_file_id": "f3"}), []) == []
    unknown = problems(user("t1", budget_line() | {"notice_file_id": "nope"}), [])
    assert any("file nope doesn't exist" in p for p in unknown)
    elsewhere = [*FILES, file("f9", grant_id="other")]
    other = problems(user("t1", budget_line() | {"notice_file_id": "f9"}), [], elsewhere)
    assert any("each grant is isolated" in p for p in other)


def test_the_agents_line_names_the_notice_it_cites():
    cites_f3 = budget_line()  # every value is cited to f3
    assert problems(agent("t1", cites_f3 | {"notice_file_id": "f3"}), []) == []
    moved = problems(agent("t1", cites_f3 | {"notice_file_id": "f2"}), [])
    assert any("belongs to the notice it cites" in p for p in moved)
    # The accountant may name any file on the grant.
    assert problems(user("t1", cites_f3 | {"notice_file_id": "f2"}), []) == []
