"""Format checks for the NSF rulebook the agent gets on every run.

Each rule is a `### <ID>` heading under a `## ` section for its kind, then its
text, then `- Kind:`, `- Source:`, optional `- Quote:` and `- Checked:` lines.
These tests check the shape only, not whether a rule is right: each rule is
checked against its source by hand.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

RULEBOOK = Path(__file__).resolve().parents[1] / "app" / "agent" / "rulebooks" / "nsf.md"

ID_PATTERN = re.compile(r"^NSF-[A-Z0-9]+(?:-[A-Z0-9]+)*$")
# A link may hold balanced parentheses, as eCFR paragraph anchors do: #p-200.475(e).
SOURCE_LINE = re.compile(r"^- Source: \[[^\]]+\]\(https://(?:[^()\s]|\([^()\s]*\))+\)$")
QUOTE_LINE = re.compile(r'^- Quote: "[^"]+" \(.+\)$')
CHECKED_LINE = re.compile(r"^- Checked: \d{4}-\d{2}-\d{2}$")
META_PREFIXES = ("- Kind: ", "- Source: ", "- Quote: ", "- Checked: ")

# Each section heading holds rules of one kind.
SECTION_KINDS = {
    "Kinds of cost allowed only under a condition": "allowed under a condition",
    "Kinds of cost that are not allowed": "not allowed",
    "Judgment rules the agent flags or compares": "judgment",
}


@dataclass
class Rule:
    id: str
    section: str
    text: list[str] = field(default_factory=list)
    meta: list[str] = field(default_factory=list)

    def lines(self, prefix: str) -> list[str]:
        return [line for line in self.meta if line.startswith(prefix)]


@dataclass
class Rulebook:
    header: str
    rules: list[Rule]


def parse(text: str) -> Rulebook:
    header_lines: list[str] = []
    rules: list[Rule] = []
    section: str | None = None
    current: Rule | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if raw.startswith("## "):
            section = raw[3:].strip()
            current = None
        elif raw.startswith("### "):
            current = Rule(id=raw[4:].strip(), section=section or "")
            rules.append(current)
        elif section is None:
            header_lines.append(raw)
        elif current is not None and line:
            (current.meta if line.startswith("- ") else current.text).append(line)
    return Rulebook(header="\n".join(header_lines), rules=rules)


@pytest.fixture(scope="module")
def rulebook() -> Rulebook:
    assert RULEBOOK.is_file(), f"rulebook missing: {RULEBOOK}"
    return parse(RULEBOOK.read_text(encoding="utf-8"))


def test_rulebook_has_rules(rulebook: Rulebook) -> None:
    assert rulebook.rules, f"no rules found in {RULEBOOK}"


def test_header_explains_kinds_and_lists_what_is_unread(rulebook: Rulebook) -> None:
    assert "How a rule's kind decides the answer" in rulebook.header
    for kind in ("not-allowed", "allowed-under-a-condition", "judgment"):
        assert kind in rulebook.header, f"header doesn't say what a {kind} rule gives"
    assert "still unread" in rulebook.header


def test_every_section_is_a_known_kind(rulebook: Rulebook) -> None:
    unknown = sorted({rule.section for rule in rulebook.rules} - SECTION_KINDS.keys())
    assert not unknown, f"rules under unknown sections: {unknown}"


def test_every_rule_has_a_well_formed_id(rulebook: Rulebook) -> None:
    bad = [rule.id for rule in rulebook.rules if not ID_PATTERN.match(rule.id)]
    assert not bad, f"rule IDs not in the NSF-WORD-WORD form: {bad}"


def test_rule_ids_are_unique(rulebook: Rulebook) -> None:
    ids = [rule.id for rule in rulebook.rules]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate rule IDs: {duplicates}"


def test_every_rule_has_text(rulebook: Rulebook) -> None:
    missing = [rule.id for rule in rulebook.rules if not rule.text]
    assert not missing, f"rules with no text: {missing}"


def test_every_meta_line_is_known(rulebook: Rulebook) -> None:
    unknown = [
        f"{rule.id}: {line}"
        for rule in rulebook.rules
        for line in rule.meta
        if not line.startswith(META_PREFIXES)
    ]
    assert not unknown, f"unknown lines, check the spelling: {unknown}"


def test_every_rule_has_one_kind_matching_its_section(rulebook: Rulebook) -> None:
    for rule in rulebook.rules:
        kinds = [line.removeprefix("- Kind:").strip() for line in rule.lines("- Kind:")]
        assert len(kinds) == 1, f"{rule.id} needs exactly one kind line"
        expected = SECTION_KINDS.get(rule.section)
        assert kinds[0] == expected, f"{rule.id} says '{kinds[0]}' under '{rule.section}'"


def test_every_rule_has_a_source_with_a_link(rulebook: Rulebook) -> None:
    for rule in rulebook.rules:
        sources = rule.lines("- Source:")
        assert sources, f"{rule.id} has no source"
        for line in sources:
            assert SOURCE_LINE.match(line), f"{rule.id} source has no https link: {line}"


def test_every_quote_is_quoted_and_attributed(rulebook: Rulebook) -> None:
    for rule in rulebook.rules:
        for line in rule.lines("- Quote:"):
            assert QUOTE_LINE.match(line), f'{rule.id} quote not "text" (source): {line}'


def test_every_rule_has_a_checked_date(rulebook: Rulebook) -> None:
    bad = [
        rule.id
        for rule in rulebook.rules
        if len([line for line in rule.meta if CHECKED_LINE.match(line)]) != 1
    ]
    assert not bad, f"rules without exactly one '- Checked: YYYY-MM-DD' line: {bad}"
