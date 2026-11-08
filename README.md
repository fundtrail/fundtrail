# FundTrail

**Automate the Old Way.** Proving that a research grant's spending followed the rules still means piecing together spreadsheets, email chains and receipts by hand at closeout. FundTrail keeps a running evidence file for every grant instead. An agent reads evidence as it arrives and writes records that cite the exact source text. Code rechecks every charge against the grant's rules and sorts each one into evidence complete, possible conflict, missing evidence or needs a human. The closeout packet is ready when the grant ends, and a person makes every final call.

**For contributors and agents:** start with [CLAUDE.md](CLAUDE.md), then [docs/](docs/).

**Status:** under construction for the BBS x Ramp Hackathon, Round 2.

**All demo data is synthetic.** See [data/demo/SYNTHETIC.md](data/demo/SYNTHETIC.md).

## Current step: citation test

```bash
cp .env.example .env   # then add your ANTHROPIC_API_KEY
uv run --env-file .env python spikes/citation_test.py
```
