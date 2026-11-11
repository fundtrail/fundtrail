-- Sample grants (issue 165, ruling 47, decision 0027): the prerun. A prerun is a sample
-- played first event to last with the real agent while a sample accountant makes the
-- scripted decisions, in a seeding workspace of its own; the grant it played is kept as
-- the saved result. It's released only when it matches the sample's expected results, and
-- it's used only while its version (the sample, the rulebook, the prompts and the model)
-- is the current one.

create table public.sample_preruns (
  id text primary key default gen_random_uuid()::text,
  seq bigint generated always as identity, -- the order they were made in
  sample text not null, -- the sample pack's ID
  version text not null, -- the hash it was made at
  grant_id text not null references public.grants (id) on delete cascade, -- the saved result
  released boolean not null default false,
  checked integer not null default 0, -- the expected buckets checked
  wrong jsonb not null default '[]', -- the ones that didn't match
  usage jsonb not null default '{}' -- model calls and tokens, from the runs' logs
);
create index sample_preruns_sample_idx on public.sample_preruns (sample, seq);

-- A sample grant opened from a prerun, and whether it's still on the run-through: every
-- accountant decision so far is the sample accountant's scripted one. Off for good once not.
create table public.sample_runthrough (
  grant_id text primary key references public.grants (id) on delete cascade,
  prerun_id text not null references public.sample_preruns (id) on delete cascade,
  off boolean not null default false,
  -- What the copied rows' new IDs are made from, new on each start, so a start over
  -- never reuses an ID or a storage path.
  salt text not null default gen_random_uuid()::text
);

create index sample_preruns_grant_id_idx on public.sample_preruns (grant_id);
create index sample_runthrough_prerun_id_idx on public.sample_runthrough (prerun_id);

-- A seeding workspace: where the prerun command plays a sample. No person is a member
-- of it, only its sample accountant. Its agent runs go on a job queue of their own, which
-- only that command's worker takes: the app's worker never runs them (they'd have no
-- spend cap), and the command never runs anyone else's.
create table public.sample_seeding (
  workspace_id text primary key references public.workspaces (id) on delete cascade,
  queue text not null unique
);

-- A move that loaded the prerun's saved result, rather than playing live.
alter table public.sample_moves add column loaded boolean not null default false;

-- As every table: row level security on, with no policies.
alter table public.sample_preruns enable row level security;
alter table public.sample_runthrough enable row level security;
alter table public.sample_seeding enable row level security;
