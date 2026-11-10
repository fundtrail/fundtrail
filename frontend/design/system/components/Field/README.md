# Field

The input basics for the accountant's answers: a label, a control, and a hint or an error under it.

**Use it** for every form field. Forms in FundTrail are short and sit inline where they settle something (see AnswerForm).

- **Structure:** `ft-field` holds `ft-field__label` (13px, 600, always visible, never a placeholder standing in for it), the control, then `ft-field__hint` (12px, `ink-muted`) or, when invalid, `ft-field__error` (12px, 600, `conflict`, with a small diamond) in the same spot.
- **Controls:** `ft-input` (`control-md` tall) and `ft-textarea`, `paper-raised` with a 1px `rule-strong` border (3:1), `radius-md`. Hover darkens the border; focus is the 2px `focus` ring plus an `ink` border. Placeholders are examples ("For example: …"), never instructions.
- **Invalid:** add `is-invalid` to the field: the border turns `conflict` and the error replaces the hint. Validate on save, not while typing, and clear the error as soon as the field is fixed.
- **Disabled:** `paper-sunken`, dashed border, `ink-muted` text.
- **Money:** `ft-money` with a `$` prefix, right-aligned tabular figures.
- **Units:** `ft-units`, two short numeric inputs: "56 of 96 samples".
- **Choice:** `ft-choice`, outlined radio chips for two or three options; the chosen one gets an `ink` border and `paper-sunken`. Use a `fieldset` and `legend`.
- **Live check:** `ft-check` states what a value would do before it is saved: dashed ring while empty, a `complete` dot when it fits ("Covers this charge"), a `needs-human` ring when it doesn't ("doesn't match the charge").

Don't: use color on neutral fields, put the label inside the box, or block typing with errors.
