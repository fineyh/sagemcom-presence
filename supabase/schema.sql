-- sagemcom-presence schema (Supabase / Postgres)
-- Apply via the Supabase MCP (apply_migration) or the SQL editor.
--
-- Privacy model: this is your home-network data. RLS is ON and NO anon/public
-- policies are created, so the public anon key can read nothing. Both the
-- collector and the dashboard's server side use the service_role key, which
-- bypasses RLS. The dashboard itself is additionally gated by a password.

-- ── devices: one row per MAC (stable-ish identity), user-editable ────────────
create table if not exists devices (
  mac           text primary key,                       -- normalized UPPER MAC
  hostname      text,                                    -- last hostname from router
  custom_name   text,                                    -- user-assigned label
  vendor        text,                                    -- OUI vendor (null if random)
  is_randomized boolean not null default false,          -- locally-administered MAC
  is_online     boolean not null default false,
  last_ip       text,
  interface     text,                                    -- WiFi / Ethernet
  first_seen    timestamptz not null default now(),
  last_seen     timestamptz not null default now(),      -- last time seen active
  hidden        boolean not null default false,          -- hide from main view
  notes         text,
  updated_at    timestamptz not null default now()
);

-- ── events: append-only online/offline transitions ───────────────────────────
create table if not exists events (
  id        bigint generated always as identity primary key,
  mac       text not null references devices(mac) on delete cascade,
  type      text not null check (type in ('online','offline')),
  ts        timestamptz not null default now(),
  ip        text,
  hostname  text
);
create index if not exists events_mac_ts_idx on events (mac, ts desc);
create index if not exists events_ts_idx       on events (ts desc);

-- ── polls: collector heartbeat (so the dashboard knows it's alive) ────────────
create table if not exists polls (
  id           bigint generated always as identity primary key,
  ts           timestamptz not null default now(),
  active_count int,
  total_count  int,
  ok           boolean not null default true,
  error        text
);
create index if not exists polls_ts_idx on polls (ts desc);

-- ── online-session view: pair each 'online' with the next 'offline' ───────────
-- Gives start/end/duration per session; open sessions have ended_at = null.
create or replace view device_sessions as
with ordered as (
  select mac, type, ts,
         lead(ts)   over (partition by mac order by ts) as next_ts,
         lead(type) over (partition by mac order by ts) as next_type
  from events
)
select
  mac,
  ts                                   as started_at,
  case when next_type = 'offline' then next_ts end as ended_at,
  case when next_type = 'offline'
       then next_ts - ts
       else now() - ts end             as duration
from ordered
where type = 'online';

-- ── RLS: lock everything down to service_role only ───────────────────────────
alter table devices enable row level security;
alter table events  enable row level security;
alter table polls   enable row level security;
-- (no policies created => anon/authenticated get nothing; service_role bypasses RLS)
