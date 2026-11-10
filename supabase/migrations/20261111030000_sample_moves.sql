-- Sample grants (issue 165): each move of a sample grant's timeline, so the timeline can
-- say what the last move played ("Just happened"). Opening a sample is a move from
-- nothing to the timeline's first event. Removed with the grant.

create table public.sample_moves (
  id bigint generated always as identity primary key,
  grant_id text not null references public.grants (id) on delete cascade,
  moved_from timestamptz, -- the grant's now before the move; null when the sample was opened
  moved_to timestamptz not null, -- the grant's now after it; moves are ordered by id
  constraint sample_moves_forward check (moved_from is null or moved_from <= moved_to)
);
create index sample_moves_grant_id_idx on public.sample_moves (grant_id, id);

-- As every table: row level security on, with no policies. The backend uses the service
-- role; the browser never reads the tables directly.
alter table public.sample_moves enable row level security;
