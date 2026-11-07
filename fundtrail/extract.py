"""Extract cited fields from a document and verify each one in code.

Flow: build a custom content document (one block per paragraph) with citations
on, ask for one "field: value" line per field, then bind each line to the
citations on the text that produced it and check the value against the cited
text. Citations cannot be combined with structured outputs, so parsing is ours.

Raw API responses are cached on disk, keyed by the file's bytes, the model, and
the prompt, so re-runs and the demo cost nothing and work without a key.

Run from the repo root:
    uv run --env-file .env python -m fundtrail.extract data/demo/award_letter.txt
    REPLAY=1 uv run python -m fundtrail.extract data/demo/award_letter.txt
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import anthropic

from fundtrail.fields import AWARD_FIELDS, FieldSpec
from fundtrail.ingest import Document, load_text_document
from fundtrail.normalize import check_value
from fundtrail.schema import ExtractionRecord

MODEL = "claude-opus-5-5"
REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "cache" / "responses"
EXTRACTIONS_DIR = REPO_ROOT / "data" / "extractions"
NOT_FOUND = "NOT FOUND"

_FIELD_LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")


class CacheMiss(RuntimeError):
    """Replay mode was asked for a response that is not cached."""


class ExtractionFailed(RuntimeError):
    """The API returned no usable answer (refusal or truncated output)."""


def build_prompt(fields: Iterable[FieldSpec]) -> str:
    lines = "\n".join(f"{f.name}: <{f.description}>" for f in fields)
    return (
        "Read the document above and extract these fields.\n\n"
        "Reply with exactly one line per field, in this order, and nothing else:\n"
        f"{lines}\n\n"
        "Rules:\n"
        "- Copy each value character for character from the document. "
        "Do not reformat dates, amounts, or names.\n"
        "- Cite the passage that states each value.\n"
        f"- If the document does not state a field, write {NOT_FOUND} as its value."
    )


def build_request(doc: Document, fields: Iterable[FieldSpec]) -> dict[str, Any]:
    return {
        "model": MODEL,
        "max_tokens": 16000,
        "output_config": {"effort": "low"},
        # Server-side fallback: if a safety classifier declines, the API retries
        # on Anthropic's recommended fallback model within the same call.
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "content",
                            "content": [{"type": "text", "text": b} for b in doc.blocks],
                        },
                        "title": doc.path.name,
                        "citations": {"enabled": True},
                    },
                    {"type": "text", "text": build_prompt(fields)},
                ],
            }
        ],
    }


def cache_path(doc: Document, fields: Iterable[FieldSpec], cache_dir: Path = CACHE_DIR) -> Path:
    prompt_hash = hashlib.sha256(build_prompt(fields).encode()).hexdigest()
    key = hashlib.sha256(f"{doc.sha256}|{MODEL}|{prompt_hash}".encode()).hexdigest()[:16]
    return cache_dir / f"{doc.doc_id}-{key}.json"


def fetch_response(
    doc: Document,
    fields: Iterable[FieldSpec],
    *,
    replay: bool = False,
    client: anthropic.Anthropic | None = None,
    cache_dir: Path = CACHE_DIR,
) -> dict[str, Any]:
    """The raw API response for this document and field list, from cache when possible."""
    fields = tuple(fields)
    path = cache_path(doc, fields, cache_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if replay:
        raise CacheMiss(f"No cached response for {doc.path.name} at {path.name}. Run once without REPLAY to create it.")
    if client is None:
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise CacheMiss("No cached response and no API key. Set ANTHROPIC_API_KEY in .env and run with --env-file .env.")
        client = anthropic.Anthropic()

    response = client.beta.messages.create(**build_request(doc, fields))
    if response.stop_reason in ("refusal", "max_tokens"):
        raise ExtractionFailed(f"{doc.path.name}: stop_reason={response.stop_reason}; nothing cached.")

    data = response.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return data


def _lines_with_citations(content: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Each line of the model's answer, with the citations on any text that overlaps it.

    The API splits an answer into several text blocks and puts citations only on
    the cited pieces, e.g. "period_end: " (no citation) + "August 31, 2025"
    (cited). Joining the blocks and tracking character spans maps every
    citation back to the line it belongs to.
    """
    full = ""
    spans: list[tuple[int, int, list[dict[str, Any]]]] = []
    for block in content:
        if block.get("type") != "text":
            continue
        start = len(full)
        full += block.get("text", "")
        spans.append((start, len(full), block.get("citations") or []))

    lines = []
    pos = 0
    for line in full.split("\n"):
        line_start, line_end = pos, pos + len(line)
        pos = line_end + 1
        cites = [c for s, e, cs in spans if s < line_end and e > line_start for c in cs]
        lines.append((line, cites))
    return lines


def _strip_wrapping(value: str) -> str:
    for pair in ('""', "''", "``"):
        if len(value) >= 2 and value[0] == pair[0] and value[-1] == pair[1]:
            return value[1:-1].strip()
    return value


def parse_response(response: dict[str, Any], doc_id: str, fields: Iterable[FieldSpec]) -> list[ExtractionRecord]:
    """One record per requested field, with its status decided in code."""
    specs = {f.name: f for f in fields}
    answers: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for line, cites in _lines_with_citations(response.get("content", [])):
        m = _FIELD_LINE.match(line)
        if m and m.group(1) in specs and m.group(1) not in answers:
            answers[m.group(1)] = (_strip_wrapping(m.group(2)), cites)

    records = []
    for name, spec in specs.items():
        base = {"doc_id": doc_id, "field": name, "kind": spec.kind}
        if name not in answers:
            records.append(ExtractionRecord(**base, value=None, cited_text=None, block=None, status="missing"))
            continue

        value, cites = answers[name]
        if value.upper() == NOT_FOUND:
            records.append(ExtractionRecord(**base, value=None, cited_text=None, block=None, status="not_found"))
            continue
        if not cites:
            normalized, _ = check_value(spec.kind, value, "")
            records.append(ExtractionRecord(
                **base, value=value, value_normalized=normalized, cited_text=None, block=None, status="no_citation",
            ))
            continue

        # Prefer the first citation that states the value; otherwise report the first one.
        chosen, ok, normalized = cites[0], False, None
        for c in cites:
            normalized, ok = check_value(spec.kind, value, c.get("cited_text", ""))
            if ok:
                chosen = c
                break
        if not ok:
            normalized, _ = check_value(spec.kind, value, chosen.get("cited_text", ""))
        records.append(ExtractionRecord(
            **base,
            value=value,
            value_normalized=normalized,
            cited_text=chosen.get("cited_text"),
            block=chosen.get("start_block_index"),
            block_end=chosen.get("end_block_index"),
            status="verified" if ok else "value_not_in_citation",
        ))
    return records


def extract_document(
    path: Path, fields: Iterable[FieldSpec] = AWARD_FIELDS, *, replay: bool = False
) -> list[ExtractionRecord]:
    doc = load_text_document(path)
    fields = tuple(fields)
    return parse_response(fetch_response(doc, fields, replay=replay), doc.doc_id, fields)


def write_records(records: list[ExtractionRecord], doc_id: str, out_dir: Path = EXTRACTIONS_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{doc_id}.json"
    path.write_text(json.dumps([r.model_dump() for r in records], indent=2) + "\n", encoding="utf-8")
    return path


def _print_table(records: list[ExtractionRecord]) -> None:
    width = max(len(r.field) for r in records)
    print(f"{'field':<{width}}  {'status':<22} {'block':<5}  value")
    for r in records:
        block = "" if r.block is None else str(r.block)
        print(f"{r.field:<{width}}  {r.status:<22} {block:<5}  {r.value if r.value is not None else '-'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract cited award fields and verify each in code.")
    parser.add_argument("path", type=Path, help="Text document to extract from, e.g. data/demo/award_letter.txt")
    parser.add_argument("--replay", action="store_true", help="Use cached responses only; never call the API.")
    args = parser.parse_args(argv)
    replay = args.replay or os.environ.get("REPLAY") == "1"

    try:
        records = extract_document(args.path, replay=replay)
    except (CacheMiss, ExtractionFailed) as e:
        print(e)
        return 2

    out = write_records(records, records[0].doc_id)
    _print_table(records)
    verified = sum(r.verified for r in records)
    print(f"\n{verified} of {len(records)} fields verified. Records written to {out.relative_to(REPO_ROOT)}")
    return 0 if verified == len(records) else 1


if __name__ == "__main__":
    sys.exit(main())
