"""The report as plain blocks, before it becomes a PDF.

content.py fills these from the inputs; pdf.py draws them. Tests read them
directly, so what the report says can be checked without reading the PDF.
"""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class Heading:
    text: str
    level: Literal[2, 3] = 2


@dataclass(frozen=True)
class Para:
    text: str
    style: Literal["body", "small", "label"] = "body"


@dataclass(frozen=True)
class Quote:
    """A passage quoted from a file, exactly as it was cited, and where it is."""

    passage: str
    source: str


@dataclass(frozen=True)
class Table:
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    widths: tuple[float, ...]  # fractions of the text width, adding up to 1
    sub_rows: frozenset[int] = frozenset()  # rows shown under the row above, such as corrections
    mono_column: int | None = None  # a column of checksums, set in a fixed-width font


@dataclass(frozen=True)
class SignLines:
    """Blank lines to fill in by hand."""

    title: str
    labels: tuple[str, ...]


Block = Heading | Para | Quote | Table | SignLines


@dataclass(frozen=True)
class Section:
    title: str
    blocks: list[Block] = field(default_factory=lambda: list[Block]())


@dataclass(frozen=True)
class ReportView:
    award_number: str
    project_title: str
    as_of: str  # the "as of" moment, written out
    signed: bool
    sections: list[Section]

    @property
    def state(self) -> str:
        return "Signed" if self.signed else "Draft"
