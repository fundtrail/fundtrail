"""Builds the two sample grants, and keeps the two unused seed grants.

Run it from `backend/`, whose environment has reportlab and pypdfium2 for the
typeset PDFs, and Pillow for the pictures:

    uv run python ../data/generator/build.py             # keeps the pictures on disk
    uv run python ../data/generator/build.py --photos    # also redraws the pictures

Writes `data/samples/<sample>/` for the larger sample (salt-marsh-carbon, the
grant that reaches closeout) and the small sample (nitrate-sensors, whose
timeline starts with its award letter): the documents, `ledger.csv`,
`timeline.json`, `user_actions.json`, `answer_key.json` and `sample.json`.
The two other seed grants, coastal-microbial-genomics and river-delta-sediment,
stay in `data/demo/` in the same format, unused for now. The samples' people,
amounts and dates are placeholders until the product owner settles them.

The output is deterministic: running it again gives the same files, byte for
byte. The samples' pictures of paper (the receipt photos, the scans and the folio's
photo) depend on the fonts on the machine, so they're redrawn only with `--photos`,
which also saves the box of every string or word on them to `image_boxes.json`.
After redrawing them, update their hashes in `data/test_seed.py`.
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

# The Add-a-grant dropdown's options each sample serves (SampleChoice). The names
# follow decision 0027's three choices. The docs give no description text, so the
# descriptions are plain words drawn from 0027 and product.md.
OPTIONS = {
    SMALL: [
        {
            "choice": "small_live",
            "name": "Small sample, read live",
            "description": "A small grant with an award letter, an invoice that arrives "
            "before its charge, and a receipt photo for you to bring in. The agent reads "
            "each arrival as the clock reaches it.",
            "placeholder": False,
        }
    ],
    LARGER: [
        {
            "choice": "larger_live",
            "name": "Larger sample, read live from the start",
            "description": "One grant of about 30 charges, from its award letter to "
            "sign-off. The agent reads each arrival as the clock reaches it, so moving "
            "the clock waits for its work.",
            "placeholder": False,
        },
        {
            "choice": "larger_prerun",
            "name": "Larger sample, prerun",
            "description": "The same grant, with the agent's work done ahead of time, "
            "so you don't wait for it.",
            "placeholder": False,
        },
    ],
}


def sample_json(g) -> str:
    from model import iso

    body = {
        "sample": g.slug,
        "award_number": g.award_number,
        "starts_at": iso(g.starts_at or g.first_event_at()),
        "last_event_at": iso(g.last_event_at()),
        "ledger_lines": len(g.lines),
        "files": len(g.docs),
        "options": OPTIONS[g.slug],
    }
    return json.dumps(body, indent=2) + "\n"


def agent_records_json(g) -> str:
    """The agent's expected records for the checks-only play, one record per line."""
    import agent_records
    from model import dump_list_obj

    body = agent_records.build(g, json.loads(g.key_json()))
    return dump_list_obj(body, "records")


def built() -> tuple[dict[str, object], list[object]]:
    """The samples by name, and the unused grants."""
    import demo
    import larger
    import scratch

    grants, _ = demo.build()
    # The larger sample is its own content now (the sample content brief). The
    # placeholder seed's Grant A is no longer written; B and C stay unused.
    unused = [g for g in grants if g.slug != LARGER]
    samples = {LARGER: larger.build(), SMALL: scratch.build()}
    return samples, unused


def main() -> None:
    import images

    images.REDRAW = "--photos" in sys.argv[1:]
    samples, unused = built()
    if images.REDRAW:
        images.save_boxes()
    # Every image is in memory before the folders are cleared.
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
        (SAMPLES / name / "agent_records.json").write_text(agent_records_json(g), encoding="utf-8")
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
