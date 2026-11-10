# Credit memo with a spaced dash

Issue 76, from the main coordinator's provisional call 38. A vendor's credit memo writes its amount with the minus set apart from the dollar sign: "- $450.00". The same amount sits on an earlier purchase line, L-8102, a $450.00 sample splitter whose own invoice hasn't arrived.

**The trap.** If the agent reads the memo as $450.00 and links it to L-8102, everything agrees in sign: the bill pays $450.00 of a $450.00 charge, and no code check objects. L-8102 would show as Evidence complete, a false clear.

**Expected:**

- The memo is read as a `bill` with a negative total, -45000 cents, as contracts.md section 1 says a credit is.
- It's linked to no charge, and the key has no link for it. A link from it to either charge is scored as wrong.
- L-8102 stays Missing evidence after the memo arrives (the check at 2026-03-24). It becomes Evidence complete only when its own invoice, INV-20388, arrives.

**Left out of the key.** L-8101's bucket after the memo arrives. The memo credits part of L-8101's invoice, INV-20417, but no credit line has posted to the ledger. Netting starts only when a ledger line that takes money off the grant names the line it corrects ([0020](../../../docs/decisions/0020-reversals-and-cost-transfers.md)). Whether the agent should flag L-8101 meanwhile isn't settled, so the key checks L-8101 only before the memo arrives.

**The check's part.** `eval/test_cases.py` reads a credit written as "-$450.00", "- $450.00" or "($450.00)" as negative. It doesn't let a positive amount match the digits of a credit, so a key that expected the memo's total as 45000 would fail.

Everything here is synthetic.
