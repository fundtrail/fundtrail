-- Issue 160: workspace membership, so one place answers who may reach a workspace or a
-- grant. Nothing a user sees changes: each workspace still has one member who can act.
-- workspaces.owner_id stays as who created it; it no longer decides access.

-- Who belongs to a workspace, and as what. "owner" can act. "sample" is for a
-- workspace's sample accountant, which can't act; it's built later with the sample
-- design.
create table public.workspace_members (
  workspace_id text not null references public.workspaces (id) on delete cascade,
  user_id uuid not null references public.users (id) on delete cascade,
  role text not null check (role in ('owner', 'sample')),
  primary key (workspace_id, user_id)
);
create index workspace_members_user_id_idx on public.workspace_members (user_id);
alter table public.workspace_members enable row level security;

-- Backfill: the creator of each existing workspace is its owner.
insert into public.workspace_members (workspace_id, user_id, role)
select id, owner_id, 'owner' from public.workspaces
on conflict do nothing;

-- Creating a workspace adds its creator as owner, in the same transaction, whatever
-- writes the row (the app, a seed or a test).
create function private.add_workspace_creator() returns trigger
  language plpgsql
  security definer
  set search_path = ''
as $$
begin
  insert into public.workspace_members (workspace_id, user_id, role)
  values (new.id, new.owner_id, 'owner')
  on conflict do nothing;
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
