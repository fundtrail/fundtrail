-- Sample grants (issue 165, ruling 47): a skipping move's walk. The grant's clock walks
-- forward in time order, event by event and scripted step by scripted step, letting the
-- agent's runs before each step finish; this row says where it's going until it gets
-- there. Removed with the grant.

create table public.sample_walks (
  grant_id text primary key references public.grants (id) on delete cascade,
  target timestamptz not null -- the move's date
);

-- As every table: row level security on, with no policies.
alter table public.sample_walks enable row level security;
