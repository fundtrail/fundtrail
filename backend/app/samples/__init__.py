"""Sample grants (issue 165).

A sample is one ordinary grant in the user's own workspace whose "now" is simulated and
which has a timeline of scheduled events: files and ledger lines arriving, and items the
user is expected to bring in. Scheduled events never change with what the user does, and
none depends on a user decision.

- `pack`: reads a sample's folder (its files, its timeline and the user actions the
  do-everything play performs).
- `timeline`: the timeline player's pure logic: what a move plays, where it stops,
  what's coming up, which items wait for the user, and the one-at-a-time rule.
"""
