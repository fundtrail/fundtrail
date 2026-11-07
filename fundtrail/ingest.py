"""Turn a source file into numbered text blocks.

Each block becomes one entry in a custom content document sent to Claude, so a
citation's block index points back to an exact paragraph we can highlight. A
citation covers a whole block, so the block is the smallest unit we can cite.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Document:
    doc_id: str
    path: Path
    sha256: str
    blocks: tuple[str, ...]


def split_blocks(text: str) -> list[str]:
    """One block per paragraph. Blank lines separate paragraphs."""
    text = text.replace("\r\n", "\n")
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def load_text_document(path: Path) -> Document:
    raw = path.read_bytes()
    return Document(
        doc_id=path.stem,
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        blocks=tuple(split_blocks(raw.decode("utf-8"))),
    )
