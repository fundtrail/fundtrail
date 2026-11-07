# FundTrail

When a research grant ends, someone has to prove every expense followed the grant's rules. FundTrail matches each expense to its receipt, approval, and governing rule, cites the exact source text, and sorts it into evidence complete, possible conflict, missing evidence, or needs a human. A person makes every final call.

**Status:** under construction for the BBS x Ramp Hackathon, Round 2.

**All demo data is synthetic.** See [data/demo/SYNTHETIC.md](data/demo/SYNTHETIC.md).

## Current step: citation test

```bash
cp .env.example .env   # then add your ANTHROPIC_API_KEY
uv run --env-file .env python spikes/citation_test.py
```
