"""Builds the demo workspace's seed and the from-scratch seed pack.

    python3 data/generator/build.py                         # standard library only
    uv run --with pillow python data/generator/build.py     # also redraws the photos

Writes data/demo/ (one folder per grant, plus seed.json) and
data/from-scratch/ (the pack the user drops in, under pack/, with its key
beside it). The output is deterministic: running it again gives the same
files, except the photos, which depend on the fonts on the machine.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
DEMO = DATA / "demo"
SCRATCH = DATA / "from-scratch"

sys.path.insert(0, str(HERE))


def main() -> None:
    import demo
    import scratch
    from model import iso

    grants, left_out = demo.build()
    pack = scratch.build()
    # Read every photo before the folders are cleared.
    for g in [*grants, pack]:
        for d in g.docs:
            d.data = bytes(d.data)

    if DEMO.exists():
        shutil.rmtree(DEMO)
    for g in grants:
        g.write(DEMO / g.slug)
        g.write_key(DEMO / g.slug)
    arrivals = sorted(
        [d.at for g in grants for d in g.docs]
        + [g.line_arrival(ln) for g in grants for ln in g.lines]
    )
    seed = {
        "opening_at": iso(demo.OPENING),
        "first_arrival_at": iso(arrivals[0]),
        "last_arrival_at": iso(arrivals[-1]),
        "arrivals_after_opening": sum(1 for t in arrivals if t > demo.OPENING),
        "grants": [
            {
                "folder": g.slug,
                "award_number": g.award_number,
                "ledger_lines": len(g.lines),
                "files": len(g.docs),
                "lines_without_buckets": left_out[g.slug],
            }
            for g in grants
        ],
    }
    (DEMO / "seed.json").write_text(json.dumps(seed, indent=2) + "\n", encoding="utf-8")

    if SCRATCH.exists():
        for child in SCRATCH.iterdir():
            if child.name != "README.md":
                shutil.rmtree(child) if child.is_dir() else child.unlink()
    pack.write(SCRATCH / "pack")
    pack.write_key(SCRATCH)
    meta = {
        "folder": "pack",
        "award_number": pack.award_number,
        "ledger_uploaded_at": iso(scratch.UPLOAD_LEDGER),
        "ledger_lines": len(pack.lines),
        "files": len(pack.docs) + 1,
    }
    (SCRATCH / "pack.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    total = sum(len(g.lines) for g in grants)
    print(
        f"demo: {len(grants)} grants, {total} ledger lines, "
        f"{sum(len(g.docs) for g in grants)} files, opening {seed['opening_at']}"
    )
    for g in grants:
        print(
            f"  {g.slug}: {len(g.lines)} lines, {len(g.docs)} files, "
            f"{len(g.buckets)} expected buckets"
        )
    print(f"from-scratch: {len(pack.lines)} lines, {len(pack.docs)} files")


if __name__ == "__main__":
    main()
