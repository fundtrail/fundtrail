-- Issue 160: workspace membership, so one place answers who may reach a workspace or a
-- grant. Nothing a user sees changes: each workspace still has one member who can act.
-- workspaces.owner_id stays as who created it; it no longer decides access.

-- Who belongs to a workspace, and as what. "owner" can act. "sample" is the workspace's
-- Sample accountant (issue 165): it can't act, and nobody signs in as it. A sample
-- grant's past decisions are written as it.
create table public.workspace_members (
  workspace_id text not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references public.users (id) on delete cascade,
  role text not null check (role in ('owner', 'sample')),
  primary key (workspace_id, user_id)
);
create index workspace_members_user_id_idx on public.workspace_members (user_id);
-- One Sample accountant per workspace.
create unique index workspace_members_one_sample on public.workspace_members (workspace_id)
  where role = 'sample';
alter table public.workspace_members enable row level security;

-- A workspace's Sample accountant: an auth user nobody can sign in as (no email, no
-- phone, no password, no identity, and banned where the auth schema has the column),
-- its users row, and its membership.
create function private.add_sample_accountant(target_workspace_id text) returns uuid
  language plpgsql
  security definer
  set search_path = ''
as $$
declare
  sample_id uuid := gen_random_uuid();
begin
  -- Only the ID is set. With instance_id and aud null, the row is outside GoTrue's
  -- instance, so GoTrue never loads it: no sign-in, admin call or token reaches it. That's
  -- deliberate.
  insert into auth.users (id) values (sample_id);
  -- Banned as well, where the column exists. A finite far date, not 'infinity': GoTrue
  -- can't read 'infinity', and if the row ever entered its instance, its admin user list
  -- would fail for every user.
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'auth' and table_name = 'users' and column_name = 'banned_until'
  ) then
    execute 'update auth.users set banned_until = ''9999-12-31 00:00:00+00'' where id = $1'
      using sample_id;
  end if;
  insert into public.users (id, email, name)
  values (sample_id, 'sample-accountant+' || target_workspace_id || '@fundtrail.example',
          'Sample accountant');
  insert into public.workspace_members (workspace_id, user_id, role)
  values (target_workspace_id, sample_id, 'sample');
  return sample_id;
end;
$$;
revoke all on function private.add_sample_accountant(text) from public;

-- Backfill: the creator of each existing workspace is its owner, and each gets its
-- Sample accountant.
insert into public.workspace_members (workspace_id, user_id, role)
select id, owner_id, 'owner' from public.workspaces
on conflict do nothing;
select private.add_sample_accountant(id) from public.workspaces;

-- Creating a workspace adds its creator as owner and its Sample accountant, in the same
-- transaction, whatever writes the row (the app, a seed or a test).
create function private.add_workspace_creator() returns trigger
  language plpgsql
  security definer
  set search_path = ''
as $$
begin
  insert into public.workspace_members (workspace_id, user_id, role)
  values (new.id, new.owner_id, 'owner')
  on conflict do nothing;
  perform private.add_sample_accountant(new.id);
  return new;
end;
$$;
revoke all on function private.add_workspace_creator() from public;
create trigger workspaces_add_creator after insert on public.workspaces
  for each row execute function private.add_workspace_creator();

-- The one access rule. The roles that can act are named here and nowhere else.
create function private.can_act(member_role text) returns boolean
  language sql
  immutable
  set search_path = ''
as $$
  select member_role = any (array['owner'])
$$;

create function private.can_reach_workspace(target_workspace_id text, member_id uuid)
  returns boolean
  language sql
  stable
  security definer
  set search_path = ''
as $$
  select exists (
    select 1 from public.workspace_members m
    where m.workspace_id = target_workspace_id
      and m.user_id = member_id
      and private.can_act(m.role)
  )
$$;

-- A grant is reached through its workspace today. A later per-grant rule changes only
-- this function.
create function private.can_reach_grant(target_grant_id text, member_id uuid)
  returns boolean
  language sql
  stable
  security definer
  set search_path = ''
as $$
  select exists (
    select 1 from public.grants g
    where g.id = target_grant_id
      and private.can_reach_workspace(g.workspace_id, member_id)
  )
$$;

revoke all on function private.can_act(text) from public;
revoke all on function private.can_reach_workspace(text, uuid) from public;
revoke all on function private.can_reach_grant(text, uuid) from public;

-- The screen pings' Realtime policy asks the same rule. The policy calls this function
-- already, so replacing its body is enough.
create or replace function private.can_hear_topic(topic text) returns boolean
  language sql
  stable
  security definer
  set search_path = ''
as $$
  select case
    when topic like 'workspace:%' then
      private.can_reach_workspace(substr(topic, length('workspace:') + 1), auth.uid())
    when topic like 'grant:%' then
      private.can_reach_grant(substr(topic, length('grant:') + 1), auth.uid())
    else false
  end;
$$;

-- A user-authored record or thread message is written by a member of its workspace.
-- An agent's or code's row has no author user, which passes (MATCH SIMPLE).
alter table public.records
  add constraint records_author_is_a_member foreign key (workspace_id, author_user_id)
    references public.workspace_members (workspace_id, user_id);
alter table public.thread_messages
  add constraint thread_messages_author_is_a_member foreign key (workspace_id, author_user_id)
    references public.workspace_members (workspace_id, user_id);
