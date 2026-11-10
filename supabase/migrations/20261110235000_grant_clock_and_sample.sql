-- Sample grants (issue 165): each sample grant has its own simulated "now", and says
-- what it was opened from. Only the two columns the contract's Grant now holds: the
-- platform (W4) moves the workspace clock onto the grant and drops it later.

alter table public.grants
  add column clock_now timestamptz, -- the grant's simulated now; null means the real date
  add column sample jsonb; -- GrantSample, set only on a sample grant
