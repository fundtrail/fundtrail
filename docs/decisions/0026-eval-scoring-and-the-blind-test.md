# 0026. The eval counts rights, wrongs and misses, and the blind test's answers stay out of the repo until it runs

**Date:** 2026-11-10 · **Status:** accepted. Reviewed by Alex on 2026-11-10 and kept as written: each expected result is right, missing or wrong, with no partial credit, and the blind set stays out of the repo until it's run, with only a checksum committed.

## Context

The eval answers "is it right?" with numbers. [eval.md](../eval.md) settles the outline: the answer key is written first, the agent and the checks are scored separately, the headline is false clears, results are counts and never percentages, and a blind test runs once at the end. It leaves open what exactly is scored, how the blind test stays blind, and how the eval runs without heavy cost.

One thing changed since the blind test was sketched. The sketch pushes the expected answers to the repo before the first run, so nobody can change an answer after seeing the result. But the app is now built by agents that read the repo. Answers in the repo are answers the builders can see.

## Decision

- **What's scored, most important first.** Items are matched the way [contracts.md](../contracts.md#14-eval-answer-key) already says: an expected item the agent matched is right, one it didn't is missing, and an item the agent wrote that the key doesn't expect is wrong. Every miss and every wrong item is listed.
  1. Each charge's bucket at each time the key names, read once every run for arrivals up to that time has finished. A charge shown as Evidence complete that shouldn't be is a false clear, counted on its own.
  2. Which checks fail for a charge. A right bucket for the wrong reason is counted on its own.
  3. Links, with their amounts.
  4. The agent's answers. An "unsure" where the key has an answer is counted on its own: it's safe, but it isn't right.
  5. Facts read from documents, and how many values couldn't be found in their file.
  6. Checklist items the agent should add, and suggestions it should make: a fix, a dispute, a duplicate.
- **No partial credit.** A link with the wrong amount counts as a missing link and a wrong one. The misses are listed one by one, so the detail is in the list, not in a score.
- **An accepted charge is never counted as Evidence complete,** and the key expects the bucket it kept. For a fully reversed charge the key expects "reversed". It's counted as reversed, never as Evidence complete and never as a false clear.
- **Two sets of cases.**
  - The working set is written by whoever builds, lives in the repo, and is used while building. Every scenario from the design discussions becomes a case.
  - The blind set is about a dozen expenses with traps, described by Alex. A separate chat with no access to the repo turns the descriptions into documents and an answer key, and Alex checks the key against his descriptions.
- **The blind set stays outside the repo until it runs.** Before the run, only a checksum of the answer key and of the documents is committed. That proves afterwards that nothing was changed, without showing the answers to anything that builds. The documents and the key are committed after the run.
- **The blind test runs once.** Its result is reported as it came out, misses included. If something is fixed afterwards, a second run is reported next to the first as "after fixes", never in its place.
- **Keeping the cost down.** The checks are plain code and run on hand-written records in the automatic checks on every pull request, for free. The agent's part runs live, on demand, with one command, and not on every pull request. Each run's results are saved with the counts and every miss.
- **Arrivals are played in order,** the way the clock replays a jump ([0023](0023-the-clock.md)), so the times in the answer key mean what they say.

## Considered and set aside

- **Committing the blind answers before the run,** as first sketched. Builders that read the repo would see them.
- **Scoring buckets only.** A charge can land in the right bucket by luck while the links behind it are wrong.
- **Percentages and weighted scores.** With a few dozen cases they suggest precision that isn't there.
- **Recorded model answers, to make runs free.** The eval would then measure a recording.

## Consequences

- The answer key's format grows to cover failing checks, checklist items and suggestions. That's a contract item and stays in [contracts.md](../contracts.md#not-decided-yet).
- A full run of the agent's part costs real model calls each time. How many runs were made is stated wherever results are reported.
- How many wrong links would mean first links need the accountant's confirmation too is still Alex's to set, before the blind run.
- How a box on a photo is measured, and what would switch photos to reading the text out first, stay open in [eval.md](../eval.md#not-decided-yet).

## For review

The calls most likely to change: no partial credit, and committing only a checksum of the blind set.
