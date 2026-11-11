-- Ruling 77: a step a Next highlight move leaves to the user is `held`: the highlight's
-- own step, and any sign-off. Unlike `left`, a later skipping move takes it up again and
-- makes it, if the user hasn't.

alter table public.sample_scripted drop constraint sample_scripted_state_check;
alter table public.sample_scripted
  add constraint sample_scripted_state_check
  check (state in ('pending', 'done', 'left', 'held'));
