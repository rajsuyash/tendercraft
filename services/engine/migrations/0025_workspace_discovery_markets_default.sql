-- 0022 shipped a column whose DEFAULT violates its own CHECK.
--
--   discovery_markets  market[] not null default '{}'
--   check (cardinality(discovery_markets) > 0)
--
-- So every insert that omits the column — POST /api/workspaces, and every workspace the
-- isolation suite creates — fails with 23514 and surfaces to the user as a bare
-- "database request failed: 400 Bad Request" under the new-workspace box. The constraint is
-- right (an empty feed must stay unreachable); the default was the part that could never
-- satisfy it.
--
-- A plain `default '{IN}'` would fix the 400 and quietly introduce the bug the constraint
-- exists to prevent: a workspace created with market='FR' would watch India and show an
-- empty-looking feed nobody configured. The default has to follow the row's own market, and
-- only a trigger can read another column, so: trigger.

create or replace function public.workspace_default_discovery_markets()
returns trigger language plpgsql as $$
begin
  if new.discovery_markets is null or cardinality(new.discovery_markets) = 0 then
    new.discovery_markets := array[new.market]::public.market[];
  end if;
  return new;
end $$;

drop trigger if exists workspace_discovery_markets_default on public.workspaces;
create trigger workspace_discovery_markets_default
  before insert on public.workspaces
  for each row execute function public.workspace_default_discovery_markets();

-- The declared default is now unreachable on insert, but leaving a constraint-violating
-- value sitting in the catalog is a trap for the next reader.
alter table public.workspaces
  alter column discovery_markets set default array['IN']::public.market[];
