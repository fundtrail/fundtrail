# FundTrail

**Automate the Old Way.** Proving that a research grant's spending followed the rules still means piecing together spreadsheets, email chains and receipts by hand at closeout. FundTrail keeps a running evidence file for every grant instead. An agent reads evidence as it arrives, writes records that cite the exact source text, matches them to charges, and answers the judgment calls, such as whether a cost is reasonable for the project. Code rechecks every clear-cut rule and sorts each charge into evidence complete, possible conflict, missing evidence or needs a human. When the grant ends, the review is already done and the proof for every charge is ready to attach to the university's closeout. A person makes every final call.

**For contributors and agents:** start with [CLAUDE.md](CLAUDE.md), then [docs/](docs/).

**Status:** under construction for the BBS x Ramp Hackathon, Round 2.

**All demo data is synthetic.** No person, award number or email address in it is real.

## What runs today

Only the shared contracts exist as code so far. Their tests run with:

```bash
PYTHONPATH=backend uv run --with pytest pytest -q backend/app/contracts/tests
```
