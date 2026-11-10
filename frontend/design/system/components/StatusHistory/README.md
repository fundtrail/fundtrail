# StatusHistory

Every change to a charge's bucket, with the date, what triggered it and a link to that trigger.

**The consumer provides** the charge's `history` (a list of `StatusEntry`): `changed_at`, the `trigger` (a record, a ledger line, an evidence file or the clock), and the bucket before and after. The API returns it oldest first; show it newest first.

- Inside the charge's details it sits closed at the bottom, in an `ft-more` disclosure: "History · 1 change".
- The trigger is a `ledger` link to the record, line or file that caused the change.
- The change reads "old badge → new badge". The first entry has only the new badge.
- Under it, in `caption`: who acted, if a person did ("Confirmed by the accountant, Apr 10, 2026."), then code's reason text.
- Plain-text form, for exports and the evidence report: "Apr 10, 2026 · new end date confirmed · Possible conflict → Evidence complete".

Don't: record entries where the bucket didn't change, or describe the clock as a person.
