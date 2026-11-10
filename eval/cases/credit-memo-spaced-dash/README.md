# Credit memo with a spaced dash

Issue 76, from the main coordinator's provisional calls 38 and 40. A vendor's credit memo writes its amount with the minus set apart from the dollar sign: "- $450.00". It credits three sieves returned from invoice INV-20417, which is charged on L-8101 ($1,200.00). The same amount, $450.00, sits on an earlier purchase line, L-8102, a sample splitter whose own invoice hasn't arrived yet.

**The trap.** An agent that matches by amount could read the memo as $450.00 and link it to L-8102. Then everything agrees in sign: the bill pays $450.00 of a $450.00 charge, no code check objects, and L-8102 shows as Evidence complete, a false clear. The trap only catches an agent that matches by amount, because the memo names L-8101's invoice.

**Expected (call 40, item 3):**

- The memo is read as a `bill` with a negative total, -45000 cents, which is how contracts.md section 1 records a credit.
- The agent links it to the charge it credits, L-8101, with the memo's own negative amount, -45000 cents. It never links it to L-8102. A positive reading, or any link to L-8102, is wrong.
- L-8101's evidence then comes to $750.00, less than the $1,200.00 the ledger charged. That puts L-8101 in Missing evidence once the memo arrives, through the checks' per-item path: `evaluate_item` in `backend/app/checks/checklist.py` finds that the bill item "A bill that adds up to the charge" ($1,200.00) has bills linked for only $750.00, so the item is missing ("the bills linked add up to $750.00 of $1,200.00"). The charge-level sum doesn't fire, because the item's amount is still the whole charge. When a ledger credit line naming L-8101 posts, the net matches and L-8101 is complete again. This case ends before that.
- L-8102 stays Missing evidence after the memo arrives (the check on 2026-03-24). It becomes Evidence complete only when its own invoice, INV-20388, arrives.

**The check's part.** `eval/test_cases.py` reads sign marks as the main coordinator's sign ruling does (call 31):

- **Either sign:** a spaced dash, as in "- $450.00", so the text alone can't settle this memo's sign. The key states it negative, by call 38.
- **Negative, and only negative:** an attached dash ("-$450.00", "$-450.00"), a true minus, a trailing minus, or "CR".
- **Positive:** a dash right after a digit or a letter ("$400-$500").

A link's amount must have the same sign as its bill's total (call 38, A1), and a bill's links, added with their signs, reach no further than its total. So a key that links the memo to L-8102 for +45000 fails, and `test_link_sign_must_match_its_bill` checks that it does.

Once a credit is on file, an Evidence complete charge's bills on file, added with their signs, must come to exactly the charge. So L-8101 marked complete after the memo fails (`test_credit_on_file_keeps_its_charge_from_complete`). Since the spaced dash is either sign, the text can't hold the key to a negative reading. `test_credit_memo_case_reads_the_memo_as_negative` asserts this case's memo total is -45000, linked to L-8101 only.

Everything here is synthetic.
