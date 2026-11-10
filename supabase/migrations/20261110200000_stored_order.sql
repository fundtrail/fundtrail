-- Stored order (issue 70): records, charges and evidence files are compared by the
-- order they were stored, never by the workspace clock. One sequence shared by the
-- three tables gives every row one number, so any two rows can be compared, even
-- rows saved in the same transaction (whose now() is the same).
--
-- A number is taken when a row is inserted, not when its transaction commits, so
-- rows of transactions running at once can interleave. Runs for one grant go one at
-- a time, so a grant's rows keep their order.
--
-- Rows already stored are numbered files and charges first and records last. On a
-- tie in time, a file stored after a record would count as new evidence for it, so
-- no existing file can look newer than an existing record.

create sequence public.stored_order as bigint;

alter table public.evidence_files
  add column stored_seq bigint not null default nextval('public.stored_order'),
  add constraint evidence_files_one_stored_seq unique (stored_seq);

alter table public.charges
  add column stored_seq bigint not null default nextval('public.stored_order'),
  add constraint charges_one_stored_seq unique (stored_seq);

alter table public.records
  add column stored_seq bigint not null default nextval('public.stored_order'),
  add constraint records_one_stored_seq unique (stored_seq);

-- Records are read in stored order.
create index records_grant_stored_seq_idx on public.records (grant_id, stored_seq);

-- Call 40: each run records the last stored point it read when it started, and the
-- agent's records carry their run's read point, set when the run saves them. For
-- an agent's answer, only what was stored after its previous answer and up to that
-- point is new evidence.
alter table public.agent_runs
  add column read_through_seq bigint;

alter table public.records
  add column read_through_seq bigint,
  add constraint records_read_through_seq_only_for_agent
    check (author = 'agent' or read_through_seq is null);
