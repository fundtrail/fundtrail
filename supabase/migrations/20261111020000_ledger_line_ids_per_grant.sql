-- Ledger line IDs are unique per grant, not per workspace (issue 165): each grant is
-- isolated, so two grants in one workspace, such as two copies of a sample, can hold
-- the same line ID. The new constraint is looser than the old one, so every existing
-- row already meets it.
alter table public.charges drop constraint charges_one_per_ledger_line;
alter table public.charges
  add constraint charges_one_per_ledger_line unique (grant_id, ledger_line_id);
