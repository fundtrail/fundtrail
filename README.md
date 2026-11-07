# FundTrail

When a research grant ends, someone has to prove every expense followed the grant's rules. FundTrail matches each expense to its receipt, approval, and governing rule, cites the exact source text, and sorts it into evidence complete, possible conflict, missing evidence, or needs a human. A person makes every final call.

**Status:** under construction for the BBS x Ramp Hackathon, Round 2.

**All demo data is synthetic.** See [data/demo/SYNTHETIC.md](data/demo/SYNTHETIC.md).

## Setup

```bash
cp .env.example .env   # then add your ANTHROPIC_API_KEY
```

## Extract cited fields from the award letter

```bash
uv run --env-file .env python -m fundtrail.extract data/demo/award_letter.txt
```

Each field comes back as one record with its cited text and block. Code marks it `verified` only if the cited text states the same value (dates compared as dates, money as cents). Raw API responses are cached in `data/cache/responses/`, keyed by the file's bytes, the model, and the prompt, so re-runs cost nothing. To run from the cache only, with no API key:

```bash
REPLAY=1 uv run python -m fundtrail.extract data/demo/award_letter.txt
```

## Tests

```bash
uv run pytest
```

The tests run offline. One fixture is the real response from the step 1 citation test (`spikes/citation_test.py`).
