-- One clock per grant (issue 165): the workspace clock moves onto its grants and goes
-- away. A grant that already has its own clock keeps it. After this, a stored clock is
-- only ever a grant's (grants.clock_now); null means the real date.

update public.grants g
   set clock_now = w.clock_now
  from public.workspaces w
 where w.id = g.workspace_id
   and w.clock_now is not null
   and g.clock_now is null;

alter table public.workspaces drop column clock_now;
