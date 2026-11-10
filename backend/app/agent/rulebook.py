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
