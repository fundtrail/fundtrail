-- Ruling 85: the highlight a Next highlight move went to, by its label, so the panel's Now
-- names it as the event the move reached, even where the clock stopped later to hold the
-- highlight's own steps. Null for any other move.
alter table public.sample_moves add column reached text;
