-- The columns the second contract change (#39) needs, on the tables of the first
-- migration. Only what #39's models add to those tables: the new tables (held
-- mail, the checker's progress, skipped files), Procrastinate's tables and the
-- Realtime policy come in a later migration.

-- Grants: decision 0025. The code in the grant's mail address, and the Drive
-- folder the accountant shared.
alter table public.grants
  add column address_code text,
  add column drive_folder_id text,
  -- Mail is routed to a grant by this code, so two grants can't share one.
  add constraint grants_one_per_address_code unique (address_code);

-- Evidence files: decision 0025. The Google type a stored PDF was exported from;
-- null for any other file.
alter table public.evidence_files
  add column exported_from text;

-- Records: the thread message whose run wrote the record. Every record the agent
-- writes in a run a thread message started waits for the accountant. Set only on
-- the agent's records.
alter table public.records
  add column thread_message_id text
    references public.thread_messages (id) on delete cascade,
  add constraint records_thread_message_id_only_for_agent
    check (author = 'agent' or thread_message_id is null);
create index records_thread_message_id_idx on public.records (thread_message_id);

-- The accountant-only kinds gain mail_action (letting in or dismissing held mail).
alter table public.records
  drop constraint records_accountant_only_kinds,
  add constraint records_accountant_only_kinds
    check (
      author = 'user'
      or kind not in ('confirmation', 'accepted_reason', 'snooze', 'sign_off', 'mail_action')
    );

-- Trigger kinds gain open_question: the ordinary run queued after a thread run
-- leaves a question open, naming the charge or record whose question is open.
alter table public.agent_runs
  drop constraint agent_runs_trigger_kind_check,
  add constraint agent_runs_trigger_kind_check
    check (trigger_kind in ('record', 'charge', 'file', 'thread_message', 'open_question', 'clock'));
alter table public.statuses
  drop constraint statuses_trigger_kind_check,
  add constraint statuses_trigger_kind_check
    check (trigger_kind in ('record', 'charge', 'file', 'thread_message', 'open_question', 'clock'));

-- Agent runs: a run a thread message started names the thread's subject, exactly
-- one of a charge or a record, so a run that fails for good can be placed on it.
-- Neither is set for any other trigger.
alter table public.agent_runs
  add column thread_charge_id text references public.charges (id) on delete cascade,
  add column thread_record_id text references public.records (id) on delete cascade,
  add constraint agent_runs_thread_subject_exactly_for_thread_message
    check (
      num_nonnulls(thread_charge_id, thread_record_id)
        = case when trigger_kind = 'thread_message' then 1 else 0 end
    );
create index agent_runs_thread_charge_id_idx on public.agent_runs (thread_charge_id);
create index agent_runs_thread_record_id_idx on public.agent_runs (thread_record_id);

-- Statuses: decision 0020, on a charge's row. The net once the lines correcting
-- the charge are netted against it (null when nothing is netted), the charges
-- netted into it, and whether it's fully reversed (the net is zero). A charge's
-- `ready` is worked out from the other fields and isn't stored.
alter table public.statuses
  add column net_cents bigint,
  add column corrections jsonb not null default '[]'::jsonb,
  add column reversed boolean not null default false,
  add constraint statuses_corrections_is_an_array
    check (jsonb_typeof(corrections) = 'array'),
  add constraint statuses_net_only_for_charge
    check (
      charge_id is not null
      or (net_cents is null and corrections = '[]'::jsonb and not reversed)
    ),
  add constraint statuses_reversed_nets_to_zero
    check (not reversed or net_cents is not distinct from 0);

-- A view's "*" is fixed when the view is made, so current_statuses is made again
-- to carry the new columns. Its definition is otherwise unchanged.
create or replace view public.current_statuses with (security_invoker = true) as
  select distinct on (grant_id, charge_id, record_id, file_id) *
  from public.statuses
  order by grant_id, charge_id, record_id, file_id, changed_at desc, id desc;
