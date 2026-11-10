# data

The two sample grants, and two more seed grants kept unused for now (issue 165). All of it is synthetic: award numbers start with `SYN-`, email addresses use the `.example` domain, and the people, vendors and documents are made up. No document here was issued by any agency or institution. The samples' content is a placeholder until it's decided.

| Path | What it is |
|---|---|
| `samples/salt-marsh-carbon/` | The larger sample: the grant that reaches closeout (Grant A below) |
| `samples/nitrate-sensors/` | The small sample: a grant whose timeline starts with its award letter and ledger |
| `samples/<sample>/timeline.json` | Its scheduled events only: files, the ledger file or each ledger line, each with its time. No user decision is in it. |
| `samples/<sample>/user_actions.json` | What the user does in the play the answer key assumes: confirming terms, and bringing in the files marked for them |
| `samples/<sample>/answer_key.json` | Each charge's expected result, in the eval's format (contracts.md section 14) |
| `samples/<sample>/sample.json` | Where its clock starts, its counts, and the Add-a-grant options it serves, with placeholder names |
| `samples/<sample>/agent_records.json` | The agent's expected records, shaped as the contract's records, for the checks-only play |
| `demo/<grant>/` | Grants B and C, in the same format, unused for now |
| `generator/` | The script that makes all of the above |
| `test_seed.py` | The test |

## The two samples

| Sample | Grant | Its clock | Lines | Files |
|---|---|---|---|---|
| `salt-marsh-carbon` (larger) | SYN-2401835, Salt Marsh Carbon Burial at Example Point. Continuing grant, Feb 1, 2024 to Jul 31, 2026, extended to Jan 31, 2027. $60,000 obligated, then $120,000. | Starts with its award letter, 2024-01-18T17:00Z, and runs its whole life, to the closeout certification's receipt on 2027-03-12 | 33 | 37 |
| `nitrate-sensors` (small) | SYN-2511958, Low-Cost Nitrate Sensors for Example Valley Groundwater. Sep 1, 2025 to Aug 31, 2028. $40,000. | Starts with its award letter, at 2026-11-16T17:30Z. Its ledger file follows at 17:45. | 7 | 10 |

There's no opening date. Every sample, in all three choices, starts at the start of its timeline and plays the same events. `starts_at` is where a sample grant's clock begins.

The larger sample serves the Add-a-grant options `larger_live` and `larger_prerun`, and the small one serves `small_live` (SampleChoice, issue 165). `sample.json` gives each option a `name` and a `description`, marked `"placeholder": true` until the docs give the words.

### The highlights (the sample content brief, ruling 58)

Each highlight's events carry a short `highlight` label in `timeline.json`, and "Next highlight" moves to the next one. Everything else is ordinary, and clears on its own.

| # | Label | In the larger sample | Expected |
|---|---|---|---|
| 1 | Terms tied to their passages | The award letter, a continuing grant with a participant support condition | Terms confirmed by the script |
| 2 | Invoice before its line | Invoice INV-20514 arrives by email on 2025-02-10; its line posts 2025-02-18 | Evidence complete once the line arrives |
| 3 | Receipt photo you deliver | A $52.00 taxi receipt photo, the PI's to deliver, on a trip whose plain text expense report rides along | Missing evidence until it's delivered |
| 4 | Shared invoice, 56 of 96 | A $10,000.00 invoice; the PI's email gives 56 of 96 samples, so $5,833.33 is this grant's; the agent's suggestion that the rest belongs to SYN-2507264 waits | Evidence complete. Decision 0021, in `shared_invoice()` |
| 5 | Own fee, own approval | The PI's own $650.00 conference fee on participant support, then her own "Approved" email | Possible conflict throughout |
| 6 | Extension found in Drive | $3,150.00 of boat time in August 2026, after the July 31 end date; extension 002, dated July 15, turns up in Drive | Possible conflict, then Evidence complete once the new end date is confirmed |
| 7 | Held vendor email, Moved off the grant | A vendor emails invoice EFG-30418 from an unknown address; let in, it shows a dinner with wine; a correcting line moves the $360.00 off the grant, with a written justification | Missing evidence, then Possible conflict after the let-in (rule NSF-NEVER-ALCOHOL), then reversed. Decision 0020, in `held_vendor_invoice()` |
| 8 | Over budget, More money, a higher limit | A $4,950.00 corer takes spending past the $60,000.00 obligated and Materials and Supplies past its line; the accountant accepts it with a note; amendment 001 adds $60,000.00 | Charges unaffected. The grant's problem is accepted |
| 9 | Closeout | The 90-day notice of expiration; the agent's closeout review; sign-off on 2027-03-10 with one item open and a note | Unmeasured by the key |
| 10 | Same invoice twice | Invoice ESS-55120 by email, then a scan in Drive six weeks later; the agent marks the scan a duplicate, and the script accepts | The charge clears from the emailed copy |
| 11 | One report, six salary lines | The postdoc's July to December 2025 effort report | All six salary lines, and their six benefit lines, clear when it arrives |
| 12 | Bill under its charge | A $1,260.00 charge with a $1,200.00 invoice; the freight bill never arrives | Missing evidence, still open at sign-off |

The small sample marks highlights 1 to 3: its award letter, invoice ESS-32410 emailed on 2026-11-19 before its line posts on 2026-12-07, and the hardware store receipt photo, the user's to deliver.

**Benefits (background, not a highlight).** Beside each of the postdoc's six salary lines is a benefit line on 53080 Benefit Assessment - Limited, at 15.00% of that month's $6,500.00, from the synthetic rate agreement (laid out like a real Colleges and Universities Rate Agreement: a fixed rate per employee group and fiscal year, July 1 to June 30). The key expects a benefit line to clear when its salary line does, which assumes the benefit check the checks builder is building.

## The timeline

`timeline.json` holds scheduled events only, in time order. Each sample has its own simulated "now", and every file arrives at that "now", with its own date as written. No scheduled event depends on what the user does. Its event kinds:

| Kind | What arrives | When |
|---|---|---|
| `file` | One document, with its `source` (`upload`, `gmail` or `drive`) and, for Gmail, its sender | At its `at` |
| `ledger` | The whole ledger file | At its `at`. Each line arrives at the later of that and 00:00 UTC on its posting date (decision 0023). The small sample uses it. |
| `ledger_line` | One seeded ledger line | At 00:00 UTC on its posting date. The larger sample uses these. |

**Files marked for the user.** A `file` event marked `"deliver": "user"` is one the user is expected to bring in, by uploading or forwarding it. Its `at` is its date. From then it waits under the timeline's Now, with Get the file and Deliver for me, until the user delivers it. The clock never delivers it (ruling 44). The small sample marks three, dated 2026-11-18T17:00Z: `hardware_receipt.jpg`, `email_invoice_ESS-32410.eml` and `invoice_EES-7420.pdf`. The larger sample marks none.

## The accountant script and the two plays

`user_actions.json` is the answer key's accountant script (ruling 47): every accountant step the key assumes, and no more, each with its time. When the user skips the human steps, the workspace's sample accountant performs these as the clock passes each one. A scripted step whose target isn't there, because the live agent did otherwise, is left for the user. Confirming terms is always a person's decision, so it lives here and never in a timeline.

Each step names its target by stable references: a ledger line ID, a file name, a record kind, and the expected decision or values. It never uses a record ID. The test holds the script to no more than the key assumes:
- a file is confirmed only if the key reads terms from it
- each step is scripted once
- after a flag answer or a typed share, the key's next bucket on that line is the one the decision clears it to: Evidence complete or Missing evidence after a supports answer or a share, and Possible conflict after a contradicts answer
- a typed share is only for part of a bill with no basis on file

A suggestion's kind must be one of the contract's record kinds that wait for the accountant. Whether a `decide_suggestion` is needed can't be checked yet, because the key doesn't express suggestions.

| Action | Fields besides `at` and an optional `note` | In the samples |
|---|---|---|
| `confirm_terms` | `file` | The award letter in both samples; the larger sample's increment (001) and extension (002) |
| `deliver_file` | `file`, a file marked for the user, delivered by upload on or after its date, so its date stays as written | The taxi photo (larger) and the hardware store photo (small), each on its date |
| `decide_suggestion` | `suggestion` (the record kind suggested, such as `checklist_removal`, `dispute`, `duplicate` or `link`), `decision` (`accept` or `reject`), and a `line_id` or a `file` | Accept the duplicate mark on the scan (larger, highlight 10) |
| `answer_flag` | `line_id`, `answer` | None: neither key expects a flag |
| `enter_share` | `line_id`, `file` (the bill), `share`, `out_of`, `basis` (decision 0021) | None |
| `let_in_mail` | `file`, a Gmail file from a sender nobody on the grant uses, held until then (ruling 59) | The vendor's email (larger, highlight 7) |
| `accept_reason` | `note` (the accountant's), `check`, an optional `problem`, and a `line_id`, a `file`, or neither for the grant (ruling 59) | Spending over the award's limit: `budget`, `over_limit`, on the grant (larger, highlight 8) |
| `sign_off` | `note` (the accountant's) (ruling 59) | The sign-off with one item open (larger, highlight 9) |

The answer key can't measure `decide_suggestion`, `let_in_mail`, `accept_reason` or `sign_off`: it doesn't express suggestions, held mail, grant problems or a sign-off. The test lets them through unmeasured, checking only that each is well formed and possible at its time. A held email counts as arriving when it's let in.

Two plays use these files. Both are W4's, in `backend/tests/samples/`:

- **Doing nothing.** No user action. Every scheduled event plays through to the end without an error. Charges are expected to wait, so no bucket is asserted.
- **Doing everything expected.** Every scripted step, at its time. Then the key's buckets hold at the key's times. A checks-only version runs in CI, on the hand-written agent records in `agent_records.json` (below). The live-agent version runs on demand, like the eval.

## The agent's expected records

`agent_records.json` holds what the agent is expected to write on each sample, for the checks-only play. The play feeds these records to the checks in place of the live agent's, with the scripted confirmations, and asserts the key's buckets. Each record is shaped as the contract's `Record` (`backend/app/contracts/records.py`), author `agent`:

- **Terms** from the award letter: the period, the notice, every budget line with its category, and the people.
- **Facts**: a bill or a note from each file the key names. A note gives its label, its statement and, for an effort report or an appointment letter, its period.
- **Links** with their amounts, parts and the default checklist item each fills. Where a note gives a share, such as "56 of the 96", the link carries the share with its three cited numbers (decision 0021).
- **Budget assignments.**
- **Allowable answers**, written again each time something new is linked. Each new one replaces the last, as the agent answers again.

IDs are placeholders the play maps to its own: the workspace is `ws-sample`, the grant `grant-<sample>`, a file `file-<file name>`, a charge `chg-<ledger line ID>`. Citations are counted, not typed:

- a text or email file gets a `char_location`
- a PDF gets a `page_location`
- a photo gets an `image_box` around the value's line, worked out from the photo's layout

Each record is written when its file and its charge have both arrived. Confirmations aren't here, because they're the accountant's and live in `user_actions.json`.

The larger sample's records also hold the agent's suggestions the highlights show: the remainder of the shared invoice (highlight 4), and the duplicate mark on the scan (highlight 10). Answers that rest on a rule name it: NSF-PARTICIPANT-NOT-STAFF for highlight 5, NSF-NEVER-ALCOHOL for highlight 7.

Within one moment, a record comes after every record it points to, the way a run writes them: terms, then facts, then links and assignments, then answers and suggestions.

The records validate against the contract's models. Played through main's checks at every key time, with the scripted steps the key measures, they give the key's bucket 8 of 8 times in the small sample. In the larger sample they give it 48 of 54 times. The six others are the benefit lines before the effort report arrives: main's checks clear a benefit line as soon as the rate agreement is linked, and the key waits for the benefit check that ties it to its salary line.

The static test checks five things:
- every link, budget line and answer the key expects is there
- every passage is at its place in its file
- every photo box lies inside its photo
- nothing is written before what it rests on
- no record comes before a record it points to

## The seed grants

Grants B and C, from the earlier placeholder seed, stay in `data/demo/` in the same format, unused. The placeholder Grant A they were built with is no longer written: the larger sample replaced it. The table and the situations below describe that placeholder seed.

| Folder | Award | Period | Where the story is | Lines | Files |
|---|---|---|---|---|---|
| `salt-marsh-carbon` (Grant A) | SYN-2401835 | Feb 1, 2024 to Jan 31, 2027 | Near its end date | 65 | 45 |
| `coastal-microbial-genomics` (Grant B) | SYN-2507264 | Jul 1, 2025 to Jun 30, 2028 | In the middle | 42 | 29 |
| `river-delta-sediment` (Grant C) | SYN-2309472 | Sep 1, 2023 to Aug 31, 2026, extended to Aug 31, 2027 | Past its old end date | 61 | 33 |

Each grant has an award letter laid out like a real NSF award notice ([domain.md](../docs/domain.md#what-an-nsf-award-notice-contains)) and ordinary charges made from templates: monthly salary lines with appointment letters and twice-yearly certified effort reports, supplies with invoices, trips with an airline receipt, a hotel folio and an expense report, and campus facility recharges with usage statements. Evidence comes as plain text, email (`.eml`), PDF (Portable Document Format) with real text, and two receipt photos.

## The situations

From [product.md, "Demo data (examples)"](../docs/product.md#demo-data-examples). They describe the placeholder seed. Its Grants B and C are kept in `data/demo/`, and its Grant A was replaced by the larger sample.

| Situation | Grant | What happens | Expected bucket |
|---|---|---|---|
| S1. The professor's own conference fee on participant support | B | A $650 registration for the principal investigator (PI) posts to 56714 Participant Support-Other on March 17, 2026. On November 24, the PI forwards her own March email saying "Approved". | Possible conflict at both times. The Allowable answer is contradicts, because the person paid is named on the grant, and the approval comes from the wrong person through the wrong channel. |
| S2. Work after the end date, then an extension | C | $3,150 of boat time in September 2026 posts on October 6, after the award letter's end date. On November 20 the no-cost extension, dated August 14, 2026, 17 days before the old end date, turns up in Drive. In the key's play, the user confirms it on November 23. | Possible conflict, still Possible conflict after the notice arrives, then Evidence complete after the confirmation. The grant's other lines dated after August 31 follow the same path. |
| S3a. A shared cost, split on an email's basis | A and B | A $10,000 invoice for one 96-reaction kit. Harper Fixture, PI on A and co-PI on B, emails that 56 of the 96 samples are for Grant A and 40 for Grant B. A is charged $5,833.33 and B $4,166.67. Each grant holds its own copy of the invoice and the email. | Evidence complete on both, with the invoice and the email linked |
| S3b. A shared cost, split on the invoice's own lines | B and C | One $2,430 invoice itemized by award: $1,450 for C and $980 for B | Evidence complete on both |
| S3c. A shared cost with nothing that gives the basis | A and C | A $1,500 invoice that names both awards. A is charged $900 and C $600, and nothing on file says why. | Needs a human on both ([0021](../docs/decisions/0021-a-cost-shared-by-two-grants.md)) |
| Participant support money moved out | B | $1,172.00 of lab reagents posts to 56714 Participant Support-Other on September 22, 2026. The agent assigns it to Materials and Supplies, so money leaves participant support, and no approval is on file. This exercises the award letter's approval rule. | Needs a human: the ledger's account disagrees with the budget line, and the Program Officer's approval is missing |
| S4. A bill before its ledger line | B | An invoice arrives by email on November 19. Its ledger line posts on December 2. | Evidence complete once the line arrives |
| The small sample | `nitrate-sensors` | Its award letter, then its ledger, then its evidence. Three files wait for the user from their date. Two lines post later, with their invoices already on file. | Evidence complete on every line once its evidence is on file. The hardware store line is Missing evidence until its photo arrives. |

## The answer keys

Each key follows [contracts.md section 14](../docs/contracts.md#14-eval-answer-key) and the eval cases in `eval/cases/`, and its times assume the play in `user_actions.json`. Ordinary charges get a bucket when their line arrives and again after each file or confirmation that changes it. A salary line stays Missing evidence until the effort report for its half year arrives, which is after that half year ends.

**Participant support.** Grant B's award letter says participant support funds can't be moved to other categories without the Program Officer's prior written approval. Following the main coordinator's provisional ruling, that rule applies only to a charge that moves money out of participant support, and the key marks it with `scope: "moved_out"` on the `approval_rule` record (the field the contracts are adding in issue 39, whose other value is `every_charge`). So the workshop's eight stipends, each paid to a participant with its participant list and payment record on file, are Evidence complete with no approval item. The reagents filed on participant support but assigned to Materials and Supplies are the one charge that moves money out, and they wait for a human.

**The test checks the rules behind the buckets, not just the files.** Nothing in a key may be Evidence complete while its cost date is outside the period in force (counting only confirmed terms), with an answer other than supports, with nothing linked, or with a ledger account whose group's category disagrees with its budget line's under the two-way rule (one contains the other, or they're the same). A link for part of a bill needs a basis (decision 0021): an item on the bill with the same amount, a note linked to the same charge, or other charges on the grant that take the rest of the bill. Where a note gives a share such as "56 of the 96", the link has to match it to within one cent.

### Left out of the keys, and why

Where an expected result depends on something the docs and the provisional decisions don't settle, the key leaves it out.

- **No benefit lines, for now.** A benefit charge can't have an expected result yet. Its default checklist item is "Benefit rate", and how that item gets filled isn't designed: a link can only point to a bill, an approval or a note, and the rate term's fields aren't settled. So nothing could check a benefit line's bucket, and the seed leaves benefit charges out until that's designed. The salary lines stay. The award letters still budget Fringe Benefits, so that line shows as unspent.
- **S1: no budget line and no Covers answer.** The agent could assign the registration to Travel or to participant support's Other, and nothing settles which. Covers is asked, since an approval is linked, but what it should answer for a professor approving her own charge isn't settled. Neither changes the bucket, which rests on the Allowable answer and on code's approver check: the wrong person, through the wrong channel.
- **S3c: no Allowable answer.** With no basis for the share, the agent may answer unsure. The bucket is Needs a human either way.
- **The `approval_rule` term's fields other than `dated`, and the `approval` record's `covers` and `channel`.** They're free text, so a key can't predict the agent's wording.
- **What the key format can't express yet:** checklist items (such as the reagents line's missing Program Officer approval), the agent's suggestions (such as S3's "the rest of this bill belongs to the other award"), problems on a bill or on the grant, and accepted charges. Two to watch for: each shared invoice's copy shows the other grant's part as money nobody charged 60 days after it arrived, unless the accountant accepts the agent's suggestion, and Grant C is past its end date until the extension is confirmed.

## Choices the docs left to the builder

- Each sample is laid out like an eval case, with `timeline.json` and `user_actions.json` in place of the eval's `arrivals.json`.
- Ledger line IDs are `L-<last four digits of the award>-<sequence>`, unique in the workspace (contracts.md section 6).
- Every Gmail arrival comes from a person named on its grant, forwarding what a vendor sent. How mail from unknown senders is held is still open.
- Emails carry no attachments: a forwarded invoice is in the email's body.
- Account codes are 5-digit codes inside the groups of domain.md's starting table. To check a charge's account against its budget line, the test carries a copy of each group's NSF categories from `backend/app/checks/account_groups.py`, because importing that table would bring in the backend's dependencies. The test reads the table's source and fails if the copy differs from it.
- The sixth sub-line of Other Direct Costs is `other_direct_costs_other`, as the contract code names it, and `eval/test_cases.py` spells it the same way.
- Award letters dated before May 20, 2024 name the policy guide in force then, NSF 23-1. Later ones name NSF 24-1.
- Airports and cities in the travel documents are made up, such as "EXC" for Example City.

The grants, people, amounts and dates are this build's picks, and the samples use them as placeholders. The samples' content is the product owner's to settle, so all of it is open to change in `generator/demo.py` and `generator/scratch.py`.

## Making it again

```
uv run --no-project --with pillow python data/generator/build.py
python3 data/test_seed.py
```

The generator uses only the standard library, except for drawing the receipt photos, which needs Pillow. Without Pillow it keeps the photos on disk. Its output is the same every time, except the photos, which depend on the machine's fonts. The test fails if any file differs from what the generator makes, so change the generator, not the files.

The test checks each ledger against section 13, each key against section 14, that every value a key expects is written in its file (PDFs read back from their text, photos from the words drawn on them, and checked against their hashes), the rules behind the buckets, and the synthetic-data rule. For the samples, it also checks that no user decision is in a timeline, that each user action is possible at its time (a file confirmed after it arrives, only a marked file delivered, on or after its date, any step about a line after the line arrives, a flag answered only where the key expects one, and a share entered only for a part of a bill the key links), and that `sample.json` agrees with the timeline and the key. A bucket that rests on an accountant decision needs its scripted step before it: Evidence complete after a flag needs the scripted answer, and on part of a bill with no basis on file it needs the scripted share, which must work out to the link to within one cent. It also checks that every SampleChoice is served by exactly one sample, with the values compared to the contract code's enum once that exists. It uses only the standard library and borrows the eval cases' checks from `eval/test_cases.py`. CI (continuous integration) runs only the backend's and frontend's checks for now, so neither test runs there yet. Running them in CI is a separate follow-up issue.
