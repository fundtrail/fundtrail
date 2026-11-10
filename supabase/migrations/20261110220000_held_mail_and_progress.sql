-- Issue 43: the mail tables of the second contract change (decision 0025), the
-- foreign key a mail_action record's held message needs, the screen pings' Realtime
-- policy, and two gaps the first migration left (contracts.md section 11).

-- Held mail: one row per message held for a grant, because its sender isn't known or
-- a known address couldn't be verified. Stored, never read by the agent, used by no
-- check. Letting it in or dismissing it is a mail_action record, so the row is never
-- updated. Rows match mail.HeldMail.
create table public.held_mail (
  id text primary key default gen_random_uuid()::text,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade,
  sender text, -- the sender's address, lower case
  reason text not null check (reason in ('unknown_sender', 'unverified_sender')),
  source_ref text not null, -- the Gmail message ID
  subject text,
  held_at timestamptz not null, -- the workspace clock's "now" when it was held
  files jsonb not null check (jsonb_typeof(files) = 'array'), -- the message first
  -- The attachments that weren't taken in, kept with the message. They reach the
  -- grant's skipped files only if it's let in.
  skipped jsonb not null default '[]'::jsonb check (jsonb_typeof(skipped) = 'array'),
  -- A message delivered to a grant's address is held once, so storing it again
  -- after a retry can't make a second row.
  constraint held_mail_one_per_message unique (grant_id, source_ref)
);
create index held_mail_workspace_id_idx on public.held_mail (workspace_id);

-- Skipped files: files Gmail or Drive brought for a grant that weren't taken in. The
-- checks raise one problem on the grant naming them. Rows match mail.SkippedFile,
-- plus an ID.
create table public.skipped_files (
  id bigint generated always as identity primary key,
  workspace_id text not null references public.workspaces (id) on delete cascade,
  grant_id text not null references public.grants (id) on delete cascade,
  name text not null,
  source text not null check (source in ('gmail', 'drive')),
  source_ref text not null, -- the Gmail message ID, or the Drive folder ID
  reason text not null check (reason in ('too_large', 'not_exportable')),
  skipped_at timestamptz not null -- the workspace clock's "now"
);
create index skipped_files_grant_id_idx on public.skipped_files (grant_id);
create index skipped_files_workspace_id_idx on public.skipped_files (workspace_id);

-- The Gmail and Drive checker's saved progress, for the app's one account: one row,
-- updated in place after each check. Rows match mail.CheckerProgress, plus a key
-- that only allows the one row.
create table public.checker_progress (
  id boolean primary key default true check (id),
  mail_cursor text, -- Gmail's position after the last check
  seen_message_ids jsonb not null default '[]'::jsonb
    check (jsonb_typeof(seen_message_ids) = 'array'),
  drive_versions jsonb not null default '[]'::jsonb
    check (jsonb_typeof(drive_versions) = 'array'),
  -- The grants whose first search has finished, never ones that only started.
  first_search_done jsonb not null default '[]'::jsonb
    check (jsonb_typeof(first_search_done) = 'array')
);

-- Held mail and skipped files are never updated, like records.
create trigger held_mail_reject_update before update on public.held_mail
  for each row execute function public.reject_update();
create trigger skipped_files_reject_update before update on public.skipped_files
  for each row execute function public.reject_update();

alter table public.held_mail enable row level security;
alter table public.skipped_files enable row level security;
alter table public.checker_progress enable row level security;

-- A mail_action record names the held message it lets in or dismisses. Generated
-- from data like charge_id and record_id, so the database enforces that it exists.
alter table public.records
  add column held_mail_id text generated always as (data ->> 'held_mail_id') stored
    references public.held_mail (id) on delete cascade;
create index records_held_mail_id_idx on public.records (held_mail_id);

-- A status row's grant is its subject's grant (section 11 keeps each grant isolated).
-- Each subject table gets a unique (id, grant_id) for the composite foreign keys to
-- point at. A grant's own status row has no subject, so nothing is checked for it.
alter table public.charges
  add constraint charges_id_grant_id unique (id, grant_id);
alter table public.records
  add constraint records_id_grant_id unique (id, grant_id);
alter table public.evidence_files
  add constraint evidence_files_id_grant_id unique (id, grant_id);
alter table public.statuses
  add constraint statuses_charge_on_its_grant foreign key (charge_id, grant_id)
    references public.charges (id, grant_id) on delete cascade,
  add constraint statuses_record_on_its_grant foreign key (record_id, grant_id)
    references public.records (id, grant_id) on delete cascade,
  add constraint statuses_file_on_its_grant foreign key (file_id, grant_id)
    references public.evidence_files (id, grant_id) on delete cascade;

-- The private evidence bucket: the first migration skipped it without a word where
-- there's no Storage schema. Now a skip says so. Where Storage exists this changes
-- nothing: the bucket is already there.
do $$
begin
  if to_regclass('storage.buckets') is null then
    raise notice 'storage.buckets does not exist, so the evidence bucket was not created';
  else
    insert into storage.buckets (id, name, public)
    values ('evidence', 'evidence', false)
    on conflict (id) do nothing;
  end if;
end;
$$;

-- Screen pings (docs/architecture.md, Screen updates): the backend broadcasts a small
-- "something changed" ping on a private Realtime channel, `grant:{grant_id}` or
-- `workspace:{workspace_id}`. A signed-in user hears a channel only when they own its
-- workspace. Our tables have row level security with no policies, so the check runs
-- in a security definer function, in a schema the API doesn't expose.
create schema if not exists private;

create function private.can_hear_topic(topic text) returns boolean
  language sql
  stable
  security definer
  set search_path = ''
as $$
  select case
    when topic like 'workspace:%' then exists (
      select 1 from public.workspaces w
      where w.id = substr(topic, length('workspace:') + 1) and w.owner_id = auth.uid()
    )
    when topic like 'grant:%' then exists (
      select 1 from public.grants g
      join public.workspaces w on w.id = g.workspace_id
      where g.id = substr(topic, length('grant:') + 1) and w.owner_id = auth.uid()
    )
    else false
  end;
$$;

revoke all on function private.can_hear_topic(text) from public;

-- Supabase's Realtime service creates realtime.messages. Where it doesn't exist, such
-- as a plain Postgres, the policy is skipped and a notice says so.
do $$
begin
  if to_regclass('realtime.messages') is null then
    raise notice 'realtime.messages does not exist, so the screen ping policy was not created';
  else
    grant usage on schema private to authenticated;
    grant execute on function private.can_hear_topic(text) to authenticated;
    create policy "owners hear their workspace and grant pings"
      on realtime.messages
      for select
      to authenticated
      using (
        realtime.messages.extension = 'broadcast'
        and private.can_hear_topic((select realtime.topic()))
      );
  end if;
end;
$$;

-- TRUNCATE ignores row level security, and Supabase grants every privilege on new
-- tables in public to anon and authenticated. Take TRUNCATE back from both on every
-- table here, the app's and Procrastinate's, and on tables made from now on.
do $$
declare
  role_name text;
begin
  foreach role_name in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = role_name) then
      execute format('revoke truncate on all tables in schema public from %I', role_name);
      execute format(
        'alter default privileges in schema public revoke truncate on tables from %I', role_name
      );
    end if;
  end loop;
end;
$$;
