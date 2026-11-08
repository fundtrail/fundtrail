-- FundTrail contract tables. Matches the Pydantic models in backend/app/contracts/.
-- Changing this file needs a PR that both Alex and Grant approve.
--
-- The backend connects with the service role key. Row level security is on with
-- no policies, so the browser can't read these tables directly.
-- IDs are text so the golden fixture's readable IDs fit. User IDs are auth UUIDs.

create table users (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  name text,
  created_at timestamptz not null default now()
);

create table workspaces (
  id text primary key default gen_random_uuid()::text,
  owner_id uuid not null references users (id) on delete cascade,
  name text not null,
  clock_now timestamptz, -- the workspace clock's "now"; null means the real date
  created_at timestamptz not null default now()
);

create table grants (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references workspaces (id) on delete cascade,
  funder text not null default 'NSF' check (funder in ('NSF')),
  award_number text,
  title text,
  created_at timestamptz not null default now()
);
create index on grants (workspace_id);

create table charges (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references workspaces (id) on delete cascade,
  grant_id text not null references grants (id) on delete cascade,
  ledger_line_id text not null,
  transaction_date date not null, -- the checks use this one
  posting_date date not null,
  arrived_at timestamptz not null, -- the clock uses this one
  amount_cents bigint not null,
  description text not null,
  account text not null,
  vendor text,
  reference text,
  original_line_id text, -- a reversal or cost transfer: the ledger_line_id it corrects
  unique (workspace_id, ledger_line_id)
);
create index on charges (grant_id);
create index on charges (workspace_id, arrived_at);

create table evidence_files (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references workspaces (id) on delete cascade,
  grant_id text not null references grants (id) on delete cascade,
  source text not null check (source in ('gmail', 'drive', 'upload')),
  name text not null,
  media_type text not null,
  storage_path text not null unique, -- in the "evidence" bucket
  sha256 text not null,
  document_date date,
  arrived_at timestamptz not null,
  sender text,
  source_ref text,
  parent_id text references evidence_files (id) on delete cascade
);
create index on evidence_files (grant_id);
create index on evidence_files (workspace_id, arrived_at);

create table records (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references workspaces (id) on delete cascade,
  grant_id text not null references grants (id) on delete cascade,
  kind text not null generated always as (data ->> 'kind') stored,
  data jsonb not null, -- the Pydantic Record.data, including "kind"
  author text not null check (author in ('agent', 'user')),
  author_user_id uuid references users (id),
  written_at timestamptz not null, -- the workspace clock's "now"
  replaces_id text unique references records (id) on delete cascade,
  created_at timestamptz not null default now(), -- real time, to order ties
  check ((author = 'user') = (author_user_id is not null)),
  check (kind <> 'retraction' or replaces_id is not null),
  check (replaces_id <> id)
);
create index on records (grant_id);
create index on records (workspace_id, written_at);

-- Status history. A row is written when a charge's status changes; the latest
-- row per charge is its current status.
create table statuses (
  id bigint generated always as identity primary key,
  workspace_id text not null references workspaces (id) on delete cascade,
  charge_id text not null references charges (id) on delete cascade,
  bucket text not null
    check (bucket in ('evidence_complete', 'possible_conflict', 'missing_evidence', 'needs_human')),
  reasons jsonb not null, -- list of Pydantic Reason
  changed_at timestamptz not null, -- the workspace clock's "now"
  trigger_kind text not null check (trigger_kind in ('record', 'charge', 'clock')),
  trigger_id text
);
create index on statuses (charge_id, changed_at);

create view current_statuses with (security_invoker = true) as
  select distinct on (charge_id) *
  from statuses
  order by charge_id, changed_at desc, id desc;

-- Records, charges and status history are append-only. Deletes stay allowed so
-- a workspace reset can clear them.
create function forbid_update() returns trigger
  language plpgsql
  set search_path = ''
as $$
begin
  raise exception '% is append-only', tg_table_name;
end;
$$;

create trigger records_append_only before update on records
  for each row execute function forbid_update();
create trigger charges_append_only before update on charges
  for each row execute function forbid_update();
create trigger statuses_append_only before update on statuses
  for each row execute function forbid_update();

alter table users enable row level security;
alter table workspaces enable row level security;
alter table grants enable row level security;
alter table charges enable row level security;
alter table evidence_files enable row level security;
alter table records enable row level security;
alter table statuses enable row level security;

-- Original evidence files: {workspace_id}/{grant_id}/{file_id}/{name}
insert into storage.buckets (id, name, public)
values ('evidence', 'evidence', false)
on conflict (id) do nothing;
