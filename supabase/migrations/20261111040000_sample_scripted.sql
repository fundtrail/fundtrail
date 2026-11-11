-- Sample grants (issue 165, ruling 47): the accountant script's steps a move made, or will
-- make, when it skipped the human steps. A step is written by the workspace's Sample
-- accountant at its own time, once the agent's runs before it are done; one whose target
-- isn't there is left for the user. Removed with the grant (a start over) or the move.

create table public.sample_scripted (
  grant_id text not null references public.grants (id) on delete cascade,
  step integer not null, -- the step's place in the pack's accountant script, in time order
  move_id bigint not null references public.sample_moves (id) on delete cascade,
  at timestamptz not null, -- the step's time
  state text not null check (state in ('pending', 'done', 'left')),
  record_id text, -- the record the step wrote, once done
  file_id text, -- the file a deliver_file step brought in, once done
  primary key (grant_id, step)
);
create index sample_scripted_move_id_idx on public.sample_scripted (move_id);

-- As every table: row level security on, with no policies. The backend uses the service
-- role; the browser never reads the tables directly.
alter table public.sample_scripted enable row level security;
