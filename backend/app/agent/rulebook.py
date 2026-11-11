"""The funder's rulebook: the whole file goes to the agent on every run.

Each rule is a `### RULE-ID` heading with a `- Kind:` line (rulebook #17). An answer names its rule
by that ID as `judgment.rule` (answer 6). The write tool refuses an ID the rulebook doesn't have.
"""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

RULEBOOKS = Path(__file__).parent / "rulebooks"

_HEADING = re.compile(r"^###\s+([A-Z][A-Z0-9-]+)\s*$", re.M)
_KIND = re.compile(r"^-\s*Kind:\s*(.+?)\s*$", re.M)


@dataclass(frozen=True)
class Rulebook:
    funder: str
    text: str
    kinds: dict[str, str]  # rule ID -> its kind, as the rulebook words it

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(self.kinds)


def parse_rulebook(funder: str, text: str) -> Rulebook:
    kinds: dict[str, str] = {}
    headings = list(_HEADING.finditer(text))
    for i, h in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        kind = _KIND.search(text, h.end(), end)
        kinds[h.group(1)] = kind.group(1) if kind else ""
    return Rulebook(funder=funder, text=text, kinds=kinds)


@cache
def load_rulebook(funder: str = "NSF") -> Rulebook:
    path = RULEBOOKS / f"{funder.lower()}.md"
    return parse_rulebook(funder, path.read_text(encoding="utf-8"))


# A link's URL may hold one level of parentheses, as in "section-200.475#p-200.475(e)".
_SOURCE = re.compile(r"^-\s*(Source|Older source):\s*\[(.+?)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")


@dataclass(frozen=True)
class RuleEntry:
    """One rule as a screen shows it: what it says in plain words, and its sources."""

    id: str
    kind: str  # as the rulebook words it, for example "not allowed"
    text: str  # the rule's paragraphs, before its list of kind and sources
    sources: tuple[tuple[str, str], ...]  # (label, url); an older source's label says so


def rule_entry(rulebook: Rulebook, rule_id: str) -> RuleEntry | None:
    """The rule with this ID, or None when the rulebook has no such rule (issue 303)."""
    heading = re.search(rf"^###\s+{re.escape(rule_id)}\s*$", rulebook.text, re.M)
    if heading is None:
        return None
    following = re.compile(r"^#", re.M).search(rulebook.text, heading.end())
    body = rulebook.text[heading.end() : following.start() if following else len(rulebook.text)]
    paragraphs: list[str] = []
    sources: list[tuple[str, str]] = []
    for block in body.strip().split("\n\n"):
        lines = block.strip().splitlines()
        if lines and lines[0].startswith("-"):
            for line in lines:
                if m := _SOURCE.match(line.strip()):
                    older = m.group(1) == "Older source"
                    sources.append(
                        (f"{m.group(2)} (older conditions)" if older else m.group(2), m.group(3))
                    )
        elif lines:
            paragraphs.append(" ".join(line.strip() for line in lines))
    return RuleEntry(
        id=rule_id,
        kind=rulebook.kinds.get(rule_id, ""),
        text="\n\n".join(paragraphs),
        sources=tuple(sources),
    )
