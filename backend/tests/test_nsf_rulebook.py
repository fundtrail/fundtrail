"""Format checks for the NSF rulebook the agent gets on every run.

Each rule is a `### <ID>` heading, its text, then `- Kind:`, `- Source:`,
optional `- Quote:` and `- Checked:` lines. These tests check the shape only,
not whether a rule is right: each rule is checked against its source by hand.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

RULEBOOK = Path(__file__).resolve().parents[1] / "app" / "agent" / "rulebooks" / "nsf.md"

ID_PATTERN = re.compile(r"^NSF-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
# A link may hold balanced parentheses, as eCFR paragraph anchors do: #p-200.475(e).
SOURCE_LINK = re.compile(r"^- Source: \[[^\]]+\]\(https://(?:[^()\s]|\([^()\s]*\))+\)$")
CHECKED = re.compile(r"^- Checked: \d{4}-\d{2}-\d{2}$")
KINDS = {"not allowed", "allowed under a condition", "judgment"}


@dataclass
class Rule:
    id: str
    text: list[str] = field(default_factory=list)
    meta: list[str] = field(default_factory=list)

    def lines(self, prefix: str) -> list[str]:
        return [line for line in self.meta if line.startswith(prefix)]


def parse_rules() -> list[Rule]:
    rules: list[Rule] = []
    current: Rule | None = None
    for raw in RULEBOOK.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if raw.startswith("## "):
            current = None
        elif raw.startswith("### "):
            current = Rule(id=raw[4:].strip())
            rules.append(current)
        elif current is not None and line:
            (current.meta if line.startswith("- ") else current.text).append(line)
    return rules


RULES = parse_rules()


def test_rulebook_has_rules() -> None:
    assert RULES, f"no rules found in {RULEBOOK}"


def test_every_rule_has_a_well_formed_id() -> None:
    bad = [rule.id for rule in RULES if not ID_PATTERN.match(rule.id)]
    assert not bad, f"rule IDs not in the NSF-WORD-WORD form: {bad}"


def test_rule_ids_are_unique() -> None:
    ids = [rule.id for rule in RULES]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate rule IDs: {duplicates}"


def test_every_rule_has_text() -> None:
    missing = [rule.id for rule in RULES if not rule.text]
    assert not missing, f"rules with no text: {missing}"


def test_every_rule_has_a_source_with_a_link() -> None:
    for rule in RULES:
        sources = rule.lines("- Source:")
        assert sources, f"{rule.id} has no source"
        for line in sources:
            assert SOURCE_LINK.match(line), f"{rule.id} source has no https link: {line}"


def test_every_rule_has_one_known_kind() -> None:
    for rule in RULES:
        kinds = [line.removeprefix("- Kind:").strip() for line in rule.lines("- Kind:")]
        assert len(kinds) == 1, f"{rule.id} needs exactly one kind line"
        assert kinds[0] in KINDS, f"{rule.id} has an unknown kind: {kinds[0]}"


def test_every_rule_has_a_checked_date() -> None:
    checked = {rule.id: [line for line in rule.meta if CHECKED.match(line)] for rule in RULES}
    bad = [rule_id for rule_id, lines in checked.items() if len(lines) != 1]
    assert not bad, f"rules without exactly one '- Checked: YYYY-MM-DD' line: {bad}"
