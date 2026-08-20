-- ============================================================================
-- Reparado – Ziel-Datenbankschema (Track F, Multi-Tenant)
-- Für Supabase/Postgres. NOCH NICHT ausgeführt – Design-Blueprint.
-- Prinzip: jede Werkstatt = ein Mandant (tenant). Row Level Security (RLS)
-- stellt sicher, dass eine Werkstatt NUR ihre eigenen Daten sieht.
-- ============================================================================

-- ---------- Mandanten (Werkstätten) ----------
create table if not exists workshops (
  id           uuid primary key default gen_random_uuid(),
  name         text not null,
  slug         text unique,                    -- für Buchungs-Widget-URL
  address      text,
  phone        text,
  email        text,
  plan         text default 'basic',           -- basic | plus | pro
  status       text default 'trial',           -- trial | active | suspended
  created_at   timestamptz default now()
);

-- ---------- Nutzer / Mitgliedschaften ----------
-- auth.users kommt von Supabase Auth (E-Mail+Passwort oder PIN-Login je Gerät).
create table if not exists memberships (
  id           uuid primary key default gen_random_uuid(),
  workshop_id  uuid not null references workshops(id) on delete cascade,
  user_id      uuid,                            -- FK auf auth.users
  name         text not null,
  role         text default 'mitarbeiter',      -- inhaber | mitarbeiter
  pin          text,                            -- lokaler Schnell-Login (gehasht)
  created_at   timestamptz default now()
);

-- ---------- App-State (Blob-Ansatz – matcht die DB-Naht in app.html) ----------
-- Schneller Migrationspfad: der komplette S-State pro Werkstatt als JSONB.
-- DB.write() → upsert hier; DB.hydrate() → select value.
create table if not exists app_data (
  workshop_id  uuid not null references workshops(id) on delete cascade,
  key          text not null default 'reparado_v1',
  value        jsonb not null,
  updated_at   timestamptz default now(),
  primary key (workshop_id, key)
);

-- ============================================================================
-- ZIEL-Normalisierung (Phase 2 – für echte API, Reporting, Skalierung).
-- Zunächst läuft alles über app_data (Blob); diese Tabellen werden schrittweise
-- befüllt, sobald einzelne Bereiche server-seitig gebraucht werden.
-- ============================================================================
-- create table customers   ( id uuid pk, workshop_id uuid, name, tel, mail, adr, firma, created_at );
-- create table orders       ( id uuid pk, workshop_id uuid, nr text, customer_id uuid, status, prio,
--                             devices jsonb, price numeric, created_at, due date, ins jsonb, source );
-- create table parts        ( id uuid pk, workshop_id uuid, name, stock int, min int, ek numeric, vk numeric, supplier );
-- create table invoices     ( id uuid pk, workshop_id uuid, nr text, kind text, total numeric,
--                             ledger_hash text, finalized_at timestamptz );   -- GoBD-Kette
-- create table bookings     ( id uuid pk, workshop_id uuid, payload jsonb, source text, created_at ); -- Widget-Eingänge
-- create table shipments    ( id uuid pk, workshop_id uuid, nr text, status, tracking, ref uuid );
-- create table contracts    ( id uuid pk, workshop_id uuid, nr text, plan text, pool jsonb, bills jsonb );
-- create table audit_log    ( id bigserial pk, workshop_id uuid, at timestamptz, actor text, action text, meta jsonb );

-- ============================================================================
-- Row Level Security (Mandantentrennung) – aktivieren beim Scharfschalten
-- ============================================================================
alter table workshops   enable row level security;
alter table memberships enable row level security;
alter table app_data    enable row level security;

-- Ein Nutzer sieht nur Werkstätten, in denen er Mitglied ist.
create policy ws_member_read on workshops for select
  using ( id in (select workshop_id from memberships where user_id = auth.uid()) );

create policy md_member_read on memberships for select
  using ( workshop_id in (select workshop_id from memberships where user_id = auth.uid()) );

create policy ad_member_all on app_data for all
  using ( workshop_id in (select workshop_id from memberships where user_id = auth.uid()) )
  with check ( workshop_id in (select workshop_id from memberships where user_id = auth.uid()) );

-- Hinweis: Schreibrechte auf workshops/memberships laufen über eine Service-Rolle
-- (Provisionierung neuer Werkstätten) bzw. Inhaber-Policies – im Server-Schritt ergänzen.
