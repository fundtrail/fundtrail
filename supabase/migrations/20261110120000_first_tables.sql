-- FundTrail's first tables: docs/contracts.md section 11.
--
-- Rows match the contract models in backend/app/contracts/, with the differences
-- section 11 lists. IDs are text, and user IDs are Supabase auth UUIDs.
--
-- The backend connects with the service role key. Row level security is on with
-- no policies, so the browser can't read these tables directly.
--
-- Records, charges, statuses and thread messages reject updates. Deletes stay
-- allowed so a workspace reset can clear them, which is why every foreign key
-- between workspace data cascades on delete.
--
-- Procrastinate's own job tables aren't here. How they relate to agent_runs is
-- still to settle.

-- Users: one row per Supabase auth user.
create table public.users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  name text,
  created_at timestamptz not null default now() -- real time
);

-- Workspaces: the name, the owner and the clock.
create table public.workspaces (
  id text primary key default gen_random_uuid()::text,
  owner_id uuid not null references public.users (id) on delete cascade,
  name text not null,
  clock_now timestamptz -- the workspace clock's "now"; null means the real date
);
create index workspaces_owner_id_idx on public.workspaces (owner_id);

-- Grants. The award number and title are empty until the award letter is read.
create table public.grants (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  funder text not null default 'NSF' check (funder in ('NSF')),
  award_number text,
  title text
);
create index grants_workspace_id_idx on public.grants (workspace_id);

-- Charges: section 6. One charge per ledger line, read by code.
create table public.charges (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade,
  ledger_line_id text not null,
  transaction_date date not null, -- when the cost happened; the checks use this one
  posting_date date not null, -- when the ledger recorded it
  arrived_at timestamptz not null, -- when it reached FundTrail; the clock uses this one
  amount_cents bigint not null, -- negative for a reversal, a transfer out or a credit
  description text not null,
  account text not null, -- the ledger's own expense category
  vendor text,
  reference text,
  original_line_id text, -- a reversal or cost transfer: the ledger_line_id it corrects
  constraint charges_one_per_ledger_line unique (workspace_id, ledger_line_id)
);
create index charges_grant_id_idx on public.charges (grant_id);
create index charges_workspace_arrived_at_idx on public.charges (workspace_id, arrived_at);

-- Evidence files: section 7. The original is in the private Storage bucket
-- "evidence" at {workspace_id}/{grant_id}/{file_id}/{name}.
create table public.evidence_files (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade, -- one grant per file for now
  source text not null check (source in ('gmail', 'drive', 'upload')),
  name text not null,
  media_type text not null,
  storage_path text not null,
  sha256 text not null, -- not unique: the same file twice is a problem code raises
  document_date date, -- the file's own date, when the source gives one
  arrived_at timestamptz not null, -- when it reached FundTrail; the clock uses this one
  sender text, -- the sender's address for Gmail
  source_ref text, -- the Gmail message ID or Drive file ID
  parent_id text references public.evidence_files (id) on delete cascade, -- an attachment's email
  constraint evidence_files_one_per_storage_path unique (storage_path)
);
create index evidence_files_grant_id_idx on public.evidence_files (grant_id);
create index evidence_files_workspace_arrived_at_idx on public.evidence_files (workspace_id, arrived_at);
create index evidence_files_parent_id_idx on public.evidence_files (parent_id);

-- Records: section 1. The envelope as columns and the record's data as JSONB.
-- The kind, the charge and the record it points to are generated from data, and
-- the last two are foreign keys, so the database enforces what links, budget
-- assignments and judgments point to.
create table public.records (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade,
  author text not null check (author in ('agent', 'user')),
  author_user_id uuid references public.users (id),
  written_at timestamptz not null, -- the workspace clock's "now"
  -- The record this one replaces. Several may replace the same one, because the
  -- agent's suggestions wait and the accountant confirms at most one.
  replaces_id text references public.records (id) on delete cascade,
  data jsonb not null,
  -- Not null, so data has to be an object with a kind.
  kind text not null generated always as (data ->> 'kind') stored,
  charge_id text generated always as (data ->> 'charge_id') stored
    references public.charges (id) on delete cascade,
  record_id text generated always as (data ->> 'record_id') stored
    references public.records (id) on delete cascade,
  created_at timestamptz not null default now(), -- real time; orders records written at the same clock time
  constraint records_author_user_id_exactly_for_user
    check ((author = 'user') = (author_user_id is not null)),
  constraint records_not_replacing_itself
    check (replaces_id <> id),
  constraint records_retraction_replaces_something
    check (kind <> 'retraction' or replaces_id is not null),
  constraint records_link_names_record_and_charge
    check (kind not in ('link', 'budget_assignment') or (record_id is not null and charge_id is not null)),
  -- confirmation, accepted reason, snooze and sign-off are the accountant's only.
  -- accepted_reason and snooze are working names until the contract code names them.
  constraint records_accountant_only_kinds
    check (author = 'user' or kind not in ('confirmation', 'accepted_reason', 'snooze', 'sign_off'))
);
create index records_grant_id_idx on public.records (grant_id);
create index records_workspace_written_at_idx on public.records (workspace_id, written_at, created_at);
create index records_charge_id_idx on public.records (charge_id);
create index records_record_id_idx on public.records (record_id);
create index records_replaces_id_idx on public.records (replaces_id);
create index records_author_user_id_idx on public.records (author_user_id);

-- Agent runs: section 9. The only table updated in place, as a run moves from
-- queued to running to done or failed. The model's trigger is split into
-- trigger_kind and trigger_id, like a status row's.
create table public.agent_runs (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade,
  -- What started the run: a charge or file arriving, an accountant's record, a
  -- message in a thread, or the clock (the closeout window opening).
  trigger_kind text not null
    check (trigger_kind in ('record', 'charge', 'file', 'thread_message', 'clock')),
  trigger_id text, -- the record, charge, file or message; null for the clock
  status text not null default 'queued'
    check (status in ('queued', 'running', 'done', 'failed')),
  clock_now timestamptz not null, -- the workspace clock's "now" the run works at
  queued_at timestamptz not null default now(), -- real time
  started_at timestamptz, -- real time
  finished_at timestamptz, -- real time
  summary text,
  error text,
  log_path text, -- the run's debug log in private storage; never shown to the accountant
  constraint agent_runs_trigger_id_unless_clock
    check ((trigger_kind = 'clock') = (trigger_id is null))
);
create index agent_runs_grant_queued_at_idx on public.agent_runs (grant_id, queued_at);
create index agent_runs_workspace_id_idx on public.agent_runs (workspace_id);
-- Runs for one grant go one at a time.
create unique index agent_runs_one_running_per_grant
  on public.agent_runs (grant_id) where status = 'running';

-- Thread messages: section 10. A thread is about a charge or a record. Messages
-- live outside the records, change nothing on their own, and are never edited.
create table public.thread_messages (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade,
  charge_id text references public.charges (id) on delete cascade,
  record_id text references public.records (id) on delete cascade,
  author text not null check (author in ('agent', 'user')),
  author_user_id uuid references public.users (id),
  run_id text references public.agent_runs (id) on delete cascade, -- the run that wrote the agent's message
  text text not null,
  written_at timestamptz not null, -- the workspace clock's "now"
  created_at timestamptz not null default now(), -- real time; orders messages written at the same clock time
  constraint thread_messages_about_one_thing
    check (num_nonnulls(charge_id, record_id) = 1),
  constraint thread_messages_author_user_id_exactly_for_user
    check ((author = 'user') = (author_user_id is not null)),
  constraint thread_messages_run_id_exactly_for_agent
    check ((author = 'agent') = (run_id is not null))
);
create index thread_messages_charge_id_idx on public.thread_messages (charge_id, written_at, created_at);
create index thread_messages_record_id_idx on public.thread_messages (record_id, written_at, created_at);
create index thread_messages_grant_id_idx on public.thread_messages (grant_id);
create index thread_messages_workspace_id_idx on public.thread_messages (workspace_id);
create index thread_messages_run_id_idx on public.thread_messages (run_id);
create index thread_messages_author_user_id_idx on public.thread_messages (author_user_id);

-- Status history: one row each time the status of a charge, a record, a file or
-- the grant itself changes. The latest row for each is in current_statuses.
-- A row is the checks' StatusEntry: a ChargeStatus when charge_id is set, a
-- RecordStatus when record_id or file_id is set, and a GrantStatus when none is.
-- Its trigger is split into trigger_kind and trigger_id.
create table public.statuses (
  id bigint generated always as identity primary key,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade,
  -- What the status is about: at most one of these. None means the grant itself,
  -- for a problem on the grant (section 8).
  charge_id text references public.charges (id) on delete cascade,
  record_id text references public.records (id) on delete cascade,
  file_id text references public.evidence_files (id) on delete cascade,
  -- A charge's bucket, reasons and checklist; set exactly for a charge.
  bucket text
    check (bucket in ('evidence_complete', 'possible_conflict', 'missing_evidence', 'needs_human')),
  reasons jsonb,
  checklist jsonb,
  -- The problems of a record, a file or the grant; set exactly when it isn't a charge.
  problems jsonb,
  flagged boolean not null, -- on the accountant's problem list
  rechecking boolean not null default false, -- the agent is answering again; charges only
  accepted boolean not null default false, -- the accountant accepted a reason
  snoozed boolean not null default false, -- the accountant snoozed it
  changed_at timestamptz not null, -- the workspace clock's "now"
  trigger_kind text not null
    check (trigger_kind in ('record', 'charge', 'file', 'thread_message', 'clock')),
  trigger_id text, -- the record, charge, file or message; null for the clock
  constraint statuses_about_at_most_one_thing
    check (num_nonnulls(charge_id, record_id, file_id) <= 1),
  constraint statuses_charge_fields_exactly_for_charge
    check (
      (charge_id is not null) = (bucket is not null)
      and (charge_id is not null) = (reasons is not null)
      and (charge_id is not null) = (checklist is not null)
    ),
  constraint statuses_problems_exactly_unless_charge
    check ((charge_id is null) = (problems is not null)),
  -- Where they're set, the lists are JSON arrays, so a JSON null or a string can't pass.
  constraint statuses_lists_are_arrays
    check (
      (reasons is null or jsonb_typeof(reasons) = 'array')
      and (checklist is null or jsonb_typeof(checklist) = 'array')
      and (problems is null or jsonb_typeof(problems) = 'array')
    ),
  constraint statuses_rechecking_only_for_charge
    check (charge_id is not null or not rechecking),
  constraint statuses_trigger_id_unless_clock
    check ((trigger_kind = 'clock') = (trigger_id is null))
);
create index statuses_grant_id_idx on public.statuses (grant_id, changed_at, id);
create index statuses_charge_id_idx on public.statuses (charge_id, changed_at, id);
create index statuses_record_id_idx on public.statuses (record_id, changed_at, id);
create index statuses_file_id_idx on public.statuses (file_id, changed_at, id);
create index statuses_workspace_id_idx on public.statuses (workspace_id);

-- The latest status for each charge, record, file or grant. At most one of the
-- three subject IDs is set, so distinct on the grant and all three gives one row
-- per subject, and one row per grant for the grant's own statuses.
create view public.current_statuses with (security_invoker = true) as
  select distinct on (grant_id, charge_id, record_id, file_id) *
  from public.statuses
  order by grant_id, charge_id, record_id, file_id, changed_at desc, id desc;

-- Records, charges, statuses and thread messages reject updates.
create function public.reject_update() returns trigger
  language plpgsql
  set search_path = ''
as $$
begin
  raise exception '% rows are never updated', tg_table_name
    using errcode = 'restrict_violation';
end;
$$;

create trigger records_reject_update before update on public.records
  for each row execute function public.reject_update();
create trigger charges_reject_update before update on public.charges
  for each row execute function public.reject_update();
create trigger statuses_reject_update before update on public.statuses
  for each row execute function public.reject_update();
create trigger thread_messages_reject_update before update on public.thread_messages
  for each row execute function public.reject_update();

-- Row level security on, with no policies.
alter table public.users enable row level security;
alter table public.workspaces enable row level security;
alter table public.grants enable row level security;
alter table public.charges enable row level security;
alter table public.evidence_files enable row level security;
alter table public.records enable row level security;
alter table public.statuses enable row level security;
alter table public.agent_runs enable row level security;
alter table public.thread_messages enable row level security;

-- The private Storage bucket for original evidence files (section 7). Skipped
-- where there's no Storage schema, such as a plain Postgres in tests.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public)
    values ('evidence', 'evidence', false)
    on conflict (id) do nothing;
  end if;
end;
$$;
