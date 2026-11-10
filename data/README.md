# data

The seed for the demo workspace and the seed pack for adding a grant from scratch, as provisional decision [0024](../docs/decisions/0024-the-seeded-demo-workspace.md) describes them. All of it is synthetic: award numbers start with `SYN-`, email addresses use the `.example` domain, and the people, vendors and documents are made up. No document here was issued by any agency or institution.

| Path | What it is |
|---|---|
| `demo/<grant>/` | One National Science Foundation (NSF) grant of the demo workspace: its files, `ledger.csv`, `answer_key.json` and `arrivals.json`, laid out like an eval case |
| `demo/seed.json` | The opening date, the first and last arrival, and each grant's lines left out of the key's buckets |
| `from-scratch/pack/` | The files the user drops in to add a grant from scratch, and nothing else |
| `from-scratch/` | The pack's `answer_key.json`, `arrivals.json`, `pack.json` and README |
| `generator/` | The script that makes all of the above |
| `test_seed.py` | The seed's test |

## The clock

- **Opening date: Monday, November 16, 2026, 17:00 UTC (Coordinated Universal Time), 9:00 in California.** The seed's first arrival is Grant C's award letter on August 14, 2023, and its last is an effort report on March 18, 2027. 19 files and ledger lines arrive after the opening date, for the clock to release ([0023](../docs/decisions/0023-the-clock.md)).
- Every seeded ledger line arrives at 00:00 UTC on its posting date, and every file at the time in `arrivals.json`.
- Grant A ends on January 31, 2027, so the demo opens inside its 90-day closeout window, which opened on November 2, 2026.

## Loading the seed

`arrivals.json` uses the eval cases' format. A loader takes its `file` and `ledger_line` events, each with its arrival time. Its `accountant` events aren't loaded: they're the script the answer key assumes, in which the accountant confirms each award letter's terms soon after it arrives, and the extension's new end date on November 23, 2026. In the demo the user does these, since the terms wait at the opening date (0024).

So the key's times before the opening date describe the seed replayed with that script, as the eval plays it. They aren't what the demo shows at the opening date, when every term still waits.

## The grants

| Folder | Award | Period | Where the story is | Lines | Files |
|---|---|---|---|---|---|
| `salt-marsh-carbon` (Grant A) | SYN-2401835 | Feb 1, 2024 to Jan 31, 2027 | Near its end date | 65 | 45 |
| `coastal-microbial-genomics` (Grant B) | SYN-2507264 | Jul 1, 2025 to Jun 30, 2028 | In the middle | 42 | 29 |
| `river-delta-sediment` (Grant C) | SYN-2309472 | Sep 1, 2023 to Aug 31, 2026, extended to Aug 31, 2027 | Past its old end date | 61 | 33 |

Each grant has an award letter laid out like a real NSF award notice ([domain.md](../docs/domain.md#what-an-nsf-award-notice-contains)) and ordinary charges made from templates: monthly salary lines with appointment letters and twice-yearly certified effort reports, supplies with invoices, trips with an airline receipt, a hotel folio and an expense report, and campus facility recharges with usage statements. Evidence comes as plain text, email (`.eml`), PDF (Portable Document Format) with real text, and two receipt photos.

## The situations

From [product.md, "Demo data (examples)"](../docs/product.md#demo-data-examples). Each charge's `note` in `arrivals.json` names its situation.

| Situation | Grant | What happens | Expected bucket |
|---|---|---|---|
| S1. The professor's own conference fee on participant support | B | A $650 registration for the principal investigator (PI) posts to 56714 Participant Support-Other on March 17, 2026. On November 24, after the opening date, the PI forwards her own March email saying "Approved". | Possible conflict at both times. The Allowable answer is contradicts, because the person paid is named on the grant, and the approval comes from the wrong person through the wrong channel. |
| S2. Work after the end date, then an extension | C | $3,150 of boat time in September 2026 posts on October 6, after the award letter's end date. On November 20 the no-cost extension, dated August 14, 2026, 17 days before the old end date, turns up in Drive. The accountant confirms it on November 23. | Possible conflict, still Possible conflict after the notice arrives, then Evidence complete after the confirmation. The grant's other lines dated after August 31 follow the same path. |
| S3a. A shared cost, split on an email's basis | A and B | A $10,000 invoice for one 96-reaction kit. Harper Fixture, PI on A and co-PI on B, emails that 56 of the 96 samples are for Grant A and 40 for Grant B. A is charged $5,833.33 and B $4,166.67. Each grant holds its own copy of the invoice and the email. | Evidence complete on both, with the invoice and the email linked |
| S3b. A shared cost, split on the invoice's own lines | B and C | One $2,430 invoice itemized by award: $1,450 for C and $980 for B | Evidence complete on both |
| S3c. A shared cost with nothing that gives the basis | A and C | A $1,500 invoice that names both awards. A is charged $900 and C $600, and nothing on file says why. | Needs a human on both ([0021](../docs/decisions/0021-a-cost-shared-by-two-grants.md)) |
| Participant support money moved out | B | $1,172.00 of lab reagents posts to 56714 Participant Support-Other on September 22, 2026. The agent assigns it to Materials and Supplies, so money leaves participant support, and no approval is on file. This exercises the award letter's approval rule. | Needs a human: the ledger's account disagrees with the budget line, and the Program Officer's approval is missing |
| S4. A bill before its ledger line | B | An invoice arrives by email on November 19, after the opening date. Its ledger line posts on December 2. | Evidence complete once the line arrives |
| A grant from scratch | Pack | See [from-scratch/README.md](from-scratch/README.md) | Evidence complete on every line |

## The answer keys

Each key follows [contracts.md section 14](../docs/contracts.md#14-eval-answer-key) and the eval cases in `eval/cases/`. Ordinary charges get a bucket when their line arrives and again after each file or confirmation that changes it. A salary line stays Missing evidence until the effort report for its half year arrives, which is after that half year ends.

**Participant support.** Grant B's award letter says participant support funds can't be moved to other categories without the Program Officer's prior written approval. Following the main coordinator's provisional ruling, that rule applies only to a charge that moves money out of participant support, and the key marks it with `scope: "moved_out"` on the `approval_rule` record (the field the contracts are adding in issue 39, whose other value is `every_charge`). So the workshop's eight stipends, each paid to a participant with its participant list and payment record on file, are Evidence complete with no approval item. The reagents filed on participant support but assigned to Materials and Supplies are the one charge that moves money out, and they wait for a human.

**The test checks the rules behind the buckets, not just the files.** Nothing in a key may be Evidence complete while its cost date is outside the period in force (counting only confirmed terms), with an answer other than supports, with nothing linked, or with a ledger account whose group's category disagrees with its budget line's under the two-way rule (one contains the other, or they're the same). A link for part of a bill needs a basis (decision 0021): an item on the bill with the same amount, a note linked to the same charge, or other charges on the grant that take the rest of the bill. Where a note gives a share such as "56 of the 96", the link has to match it to within one cent.

### Left out of the keys, and why

Where an expected result depends on something the docs and the provisional decisions don't settle, the key leaves it out.

- **No benefit lines, for now.** A benefit charge can't have an expected result yet. Its default checklist item is "Benefit rate", and how that item gets filled isn't designed: a link can only point to a bill, an approval or a note, and the rate term's fields aren't settled. So nothing could check a benefit line's bucket, and the seed leaves benefit charges out until that's designed. The salary lines stay. The award letters still budget Fringe Benefits, so that line shows as unspent.
- **S1: no budget line and no Covers answer.** The agent could assign the registration to Travel or to participant support's Other, and nothing settles which. Covers is asked, since an approval is linked, but what it should answer for a professor approving her own charge isn't settled. Neither changes the bucket, which rests on the Allowable answer and on code's approver check: the wrong person, through the wrong channel.
- **S3c: no Allowable answer.** With no basis for the share, the agent may answer unsure. The bucket is Needs a human either way.
- **The `approval_rule` term's fields other than `dated`, and the `approval` record's `covers` and `channel`.** They're free text, so a key can't predict the agent's wording.
- **What the key format can't express yet:** checklist items (such as the reagents line's missing Program Officer approval), the agent's suggestions (such as S3's "the rest of this bill belongs to the other award"), problems on a bill or on the grant, and accepted charges. Two to watch for: each shared invoice's copy shows the other grant's part as money nobody charged 60 days after it arrived, unless the accountant accepts the agent's suggestion, and Grant C at the opening date is past its end date until the extension is confirmed.

## Choices the docs left to the builder

- The seed is laid out like the eval cases, so the eval's runner can score it.
- Ledger line IDs are `L-<last four digits of the award>-<sequence>`, unique in the workspace (contracts.md section 6).
- Every Gmail arrival comes from a person named on its grant, forwarding what a vendor sent. How mail from unknown senders is held is still open.
- Emails carry no attachments: a forwarded invoice is in the email's body.
- Account codes are 5-digit codes inside the groups of domain.md's starting table. The test carries its own copy of each group's NSF categories, taken from the account groups table proposed in pull request 30, to check a charge's account against its budget line. It should give way to that table once the table is on main.
- The sixth sub-line of Other Direct Costs is `other_direct_costs_other`, as the contract code names it. Aligning `eval/test_cases.py`, which still spells it `other`, is a separate follow-up issue.
- Award letters dated before May 20, 2024 name the policy guide in force then, NSF 23-1. Later ones name NSF 24-1.
- Airports and cities in the travel documents are made up, such as "EXC" for Example City.

The grants, people, amounts and dates are this build's picks. Demo data specifics are the product owner's to settle ([product.md](../docs/product.md#not-decided-yet)), so all of it is open to change in `generator/demo.py`.

## Making it again

```
uv run --no-project --with pillow python data/generator/build.py
python3 data/test_seed.py
```

The generator uses only the standard library, except for drawing the receipt photos, which needs Pillow. Without Pillow it keeps the photos on disk. Its output is the same every time, except the photos, which depend on the machine's fonts. The test fails if any file differs from what the generator makes, so change the generator, not the files.

The test checks each ledger against section 13, each key against section 14, that every value a key expects is written in its file (PDFs read back from their text, photos from the words drawn on them, and checked against their hashes), the rules behind the buckets, the synthetic-data rule, and what 0024 asks of the seed. It uses only the standard library and borrows the eval cases' checks from `eval/test_cases.py`. CI (continuous integration) runs only the backend's and frontend's checks for now, so neither test runs there yet. Running them in CI is a separate follow-up issue.
