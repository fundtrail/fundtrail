"""Citation test, step 1 of the FundTrail build plan.

Sends the synthetic award letter to Claude as a custom content document
(one block per paragraph) with citations on, asks for a single
"period_end: <value>" line, saves the raw response, and reports whether
any citation's text contains the value.

Run from the repo root:
    uv run --env-file .env python spikes/citation_test.py
"""

import os
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
AWARD_PATH = ROOT / "data" / "demo" / "award_letter.txt"
OUT_PATH = ROOT / "spikes" / "out" / "citation_test_step1.json"
MODEL = "claude-opus-5-5"

PROMPT = """Read the award document above.

Reply with exactly one line and nothing else:
period_end: <end date of the period of performance, copied character for character from the document>

Cite the passage that states the date. If the document does not state it, reply:
period_end: NOT FOUND"""


def split_blocks(text: str) -> list[str]:
    """One block per paragraph. Blank lines separate paragraphs."""
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def main() -> int:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("No API key found. Copy .env.example to .env, set ANTHROPIC_API_KEY, and run with --env-file .env.")
        return 2

    blocks = split_blocks(AWARD_PATH.read_text(encoding="utf-8"))
    print(f"Sending {AWARD_PATH.name} as {len(blocks)} blocks to {MODEL}")

    client = anthropic.Anthropic()
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            # Server-side fallback: if a safety classifier declines, the API
            # retries on Anthropic's recommended fallback model in the same call.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "content",
                                "content": [{"type": "text", "text": b} for b in blocks],
                            },
                            "title": AWARD_PATH.name,
                            "citations": {"enabled": True},
                        },
                        {"type": "text", "text": PROMPT},
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError:
        print("No valid API key. Copy .env.example to .env and set ANTHROPIC_API_KEY.")
        return 2

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(response.to_json(), encoding="utf-8")
    print(f"Saved raw response to {OUT_PATH.relative_to(ROOT)}")
    print(f"Answered by: {response.model}   stop_reason: {response.stop_reason}")

    if response.stop_reason == "refusal":
        print("Request was declined. See the saved response.")
        return 1

    text_blocks = [b for b in response.content if b.type == "text"]
    full_text = "".join(b.text for b in text_blocks)
    line = next(
        (ln.strip() for ln in full_text.splitlines() if ln.strip().startswith("period_end:")),
        None,
    )
    citations = [c for b in text_blocks for c in (b.citations or [])]

    print(f"\nModel text: {full_text.strip()!r}")
    print(f"Citations returned: {len(citations)}")
    for c in citations:
        print(
            f"  - {c.type}  blocks {getattr(c, 'start_block_index', '?')}"
            f" to {getattr(c, 'end_block_index', '?')}: {c.cited_text!r}"
        )

    if line is None:
        print("\nFAIL: no 'period_end:' line in the response.")
        return 1

    value = line.split(":", 1)[1].strip()
    supported = [c for c in citations if value and value in c.cited_text]
    if supported:
        print(f"\nPASS: value {value!r} appears in {len(supported)} cited passage(s).")
        return 0
    print(f"\nFAIL: value {value!r} does not appear in any cited text.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
