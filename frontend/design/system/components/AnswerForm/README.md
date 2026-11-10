# AnswerForm

The accountant's answers, inline in the evidence trail at the link they settle: answering a question the agent was unsure about, overruling an answer, or entering a split that nothing on file gives.

**Use it** under a trail link whose verdict is the accountant's to give (`action: 'answer'` or `'split'`). Never in a dialog, never on another page: the evidence stays in view while the accountant decides.

**The consumer provides** the question or the receipt to split, the charge amount, and the save handler. The answer becomes a judgment record by the accountant; the split becomes a link with an amount.

- **Answer:** a choice (`ft-choice`) in plain words ("For this project", "Not for this project"), then **Why** (`ft-textarea`), required: it goes into the evidence report as the accountant's reasoning. Save is a neutral main button ("Save answer"), enabled once a choice is made; an empty reason shows the error on save.
- **Overrule:** a quiet `ft-overrule` link ("Overrule") beside an agent's verdict opens the same form with the other answer preselected. The agent's answer stays visible below the accountant's.
- **Split:** "Split by" Share of units or Amount; the share ("56 of 96 samples") or the amount; **Basis**, required. A live check (`ft-check`) shows before saving whether the part covers the charge and what is left for the other grant. Saving a part that doesn't match is allowed: the charge stays with the accountant, and the result says so.
- **After saving**, the link becomes the accountant's (verdict "You support", or the part's amount), its reasoning stays visible under it, the charge rechecks with the same motion as Confirm, and the result with Undo appears at the end of the trail.
- **The form never uses approve or reject colors.** Green and red are for Approve and Reject; an answer is neither.

Don't: ask for confirmation, hide the agent's reasoning while the accountant answers, or let a split be saved without a basis.
