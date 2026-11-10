-- Stored order (issue 70): records, charges and evidence files are compared by the
-- order they were stored, never by the workspace clock. One sequence shared by the
-- three tables gives every row one number, so any two rows can be compared, even
-- rows saved in the same transaction (whose now() is the same).

create sequence public.stored_order as bigint;

alter table public.records
  add column stored_seq bigint not null default nextval('public.stored_order'),
  add constraint records_one_stored_seq unique (stored_seq);

alter table public.charges
  add column stored_seq bigint not null default nextval('public.stored_order'),
  add constraint charges_one_stored_seq unique (stored_seq);

alter table public.evidence_files
  add column stored_seq bigint not null default nextval('public.stored_order'),
  add constraint evidence_files_one_stored_seq unique (stored_seq);

-- Records are read in stored order.
create index records_grant_stored_seq_idx on public.records (grant_id, stored_seq);
