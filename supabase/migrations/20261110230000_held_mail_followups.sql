-- Follow-ups from the review of issue 43's migration (20261110220000).

-- A mail_action record's held message is on the record's own grant (section 11 keeps
-- each grant isolated), the same composite-key pattern as a status row's subject. A
-- record that names no held message isn't checked.
alter table public.held_mail
  add constraint held_mail_id_grant_id unique (id, grant_id);
alter table public.records
  add constraint records_held_mail_on_its_grant foreign key (held_mail_id, grant_id)
    references public.held_mail (id, grant_id) on delete cascade;

-- The screen ping policy also requires the message's own topic to be the channel the
-- user joined and is allowed to hear. Without it, a user allowed on one channel could
-- read the broadcast rows of every other channel with a query of their own.
do $$
begin
  if to_regclass('realtime.messages') is null then
    raise notice 'realtime.messages does not exist, so the screen ping policy was not changed';
  else
    drop policy if exists "owners hear their workspace and grant pings" on realtime.messages;
    create policy "owners hear their workspace and grant pings"
      on realtime.messages
      for select
      to authenticated
      using (
        realtime.messages.extension = 'broadcast'
        and realtime.messages.topic = (select realtime.topic())
        and private.can_hear_topic((select realtime.topic()))
      );
  end if;
end;
$$;

-- A note on the TRUNCATE revoke in 20261110220000: its `alter default privileges`
-- names no role, so it covers only tables made later by the role that ran the
-- migrations (`postgres` on Supabase). A table another role makes in public still
-- gets Supabase's default grants, TRUNCATE included, and needs its own revoke.
