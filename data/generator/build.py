"""Builds the two sample grants, and keeps the two unused seed grants.

    python3 data/generator/build.py                         # standard library only
    uv run --with pillow python data/generator/build.py     # also redraws the photos

Writes `data/samples/<sample>/` for the larger sample (salt-marsh-carbon, the
grant that reaches closeout) and the small sample (nitrate-sensors, whose
timeline starts with its award letter): the documents, `ledger.csv`,
`timeline.json`, `user_actions.json`, `answer_key.json` and `sample.json`.
The two other seed grants, coastal-microbial-genomics and river-delta-sediment,
stay in `data/demo/` in the same format, unused for now. The samples' content is
a placeholder until it's decided.

The output is deterministic: running it again gives the same files, except the
photos, which depend on the fonts on the machine.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
SAMPLES = DATA / "samples"
DEMO = DATA / "demo"

sys.path.insert(0, str(HERE))

LARGER = "salt-marsh-carbon"
SMALL = "nitrate-sensors"

# The Add-a-grant dropdown's options each sample serves (SampleChoice), with
# placeholder words until the docs give them.
OPTIONS = {
    SMALL: [
        {
            "choice": "small_live",
            "name": "Placeholder: a new grant from its award letter",
            "description": "Placeholder until the docs give the words. A small grant that "
            "starts with its award letter and ledger, with a few files for you to bring in.",
            "placeholder": True,
        }
    ],
    LARGER: [
        {
            "choice": "larger_live",
            "name": "Placeholder: a grant near closeout, read live",
            "description": "Placeholder until the docs give the words. A three-year grant "
            "that opens near its end date. The agent reads its past while you watch.",
            "placeholder": True,
        },
        {
            "choice": "larger_prerun",
            "name": "Placeholder: a grant near closeout, already read",
            "description": "Placeholder until the docs give the words. The same grant, with "
            "its past already read, so it opens at once.",
            "placeholder": True,
        },
    ],
}


def sample_json(g) -> str:
    from model import iso

    body = {
        "sample": g.slug,
        "award_number": g.award_number,
        "starts_at": iso(g.starts_at or g.first_event_at()),
        "opens_at": iso(g.opens_at or g.first_event_at()),
        "last_event_at": iso(g.last_event_at()),
        "ledger_lines": len(g.lines),
        "files": len(g.docs),
        "options": OPTIONS[g.slug],
    }
    return json.dumps(body, indent=2) + "\n"


def built() -> tuple[dict[str, object], list[object]]:
    """The samples by name, and the unused grants."""
    import demo
    import scratch

    grants, _ = demo.build()
    by_slug = {g.slug: g for g in grants}
    for g in grants:
        g.opens_at = demo.OPENING
    samples = {LARGER: by_slug.pop(LARGER), SMALL: scratch.build()}
    return samples, list(by_slug.values())


def main() -> None:
    samples, unused = built()
    # Read every photo before the folders are cleared.
    for g in [*samples.values(), *unused]:
        for d in g.docs:
            d.data = bytes(d.data)

    for folder in (SAMPLES, DEMO, DATA / "from-scratch"):
        if folder.exists():
            shutil.rmtree(folder)
    for name, g in samples.items():
        g.write(SAMPLES / name)
        g.write_key(SAMPLES / name)
        (SAMPLES / name / "sample.json").write_text(sample_json(g), encoding="utf-8")
    for g in unused:
        g.write(DEMO / g.slug)
        g.write_key(DEMO / g.slug)

    for name, g in samples.items():
        print(
            f"sample {name}: {len(g.lines)} lines, {len(g.docs)} files, "
            f"{len(g.buckets)} expected buckets, {len(g.user_actions)} user actions"
        )
    for g in unused:
        print(f"unused {g.slug}: {len(g.lines)} lines, {len(g.docs)} files")


if __name__ == "__main__":
    main()
