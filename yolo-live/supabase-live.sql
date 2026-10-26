-- YOLO realtime extension / 2026-10-27
-- 区画の位置や既存レイアウトは変更しません。
-- 自宅実験の配信公開は初期値 false。秘密鍵は利用しません。
create table if not exists public.parking_live_access (
  facility_id text not null references public.parking_layouts(facility_id) on delete cascade,
  member_id uuid not null,
  primary key (facility_id, member_id)
);
alter table public.parking_live_access enable row level security;
revoke all on table public.parking_live_access from anon, authenticated;
grant select on public.parking_live_access to authenticated;
create policy "live access read own" on public.parking_live_access
  for select to authenticated using (member_id = (select auth.uid()));

create table if not exists public.parking_live_visibility (
  facility_id text primary key references public.parking_layouts(facility_id) on delete cascade,
  is_published boolean not null default false,
  updated_at timestamptz not null default now()
);
alter table public.parking_live_visibility enable row level security;
revoke all on table public.parking_live_visibility from anon, authenticated;
grant select on public.parking_live_visibility to anon, authenticated;
grant update on public.parking_live_visibility to authenticated;
create policy "live visibility public published read" on public.parking_live_visibility
  for select to anon using (is_published = true);
create policy "live visibility member read" on public.parking_live_visibility
  for select to authenticated using (
    exists (select 1 from public.parking_live_access a
            where a.facility_id = parking_live_visibility.facility_id
              and a.member_id = (select auth.uid()))
    or is_published = true
  );
create policy "live visibility member update" on public.parking_live_visibility
  for update to authenticated
  using (exists (select 1 from public.parking_live_access a
                 where a.facility_id = parking_live_visibility.facility_id
                   and a.member_id = (select auth.uid())))
  with check (exists (select 1 from public.parking_live_access a
                      where a.facility_id = parking_live_visibility.facility_id
                        and a.member_id = (select auth.uid())));

insert into public.parking_live_visibility (facility_id, is_published)
select facility_id, false from public.parking_layouts
on conflict (facility_id) do nothing;

alter table public.parking_live_status
  drop constraint if exists parking_live_status_status_check;
alter table public.parking_live_status
  add constraint parking_live_status_status_check
  check (status in ('available', 'occupied', 'blocked', 'unknown'));

revoke all on public.parking_live_status from anon, authenticated;
grant select on public.parking_live_status to anon, authenticated;
grant insert, update on public.parking_live_status to authenticated;
create policy "live published read" on public.parking_live_status
  for select to anon using (
    exists (select 1 from public.parking_live_visibility v
            where v.facility_id = parking_live_status.facility_id
              and v.is_published = true)
  );
create policy "live members read" on public.parking_live_status
  for select to authenticated using (
    exists (select 1 from public.parking_live_access a
            where a.facility_id = parking_live_status.facility_id
              and a.member_id = (select auth.uid()))
  );
create policy "live members insert" on public.parking_live_status
  for insert to authenticated with check (
    exists (select 1 from public.parking_live_access a
            where a.facility_id = parking_live_status.facility_id
              and a.member_id = (select auth.uid()))
  );
create policy "live members update" on public.parking_live_status
  for update to authenticated
  using (exists (select 1 from public.parking_live_access a
                 where a.facility_id = parking_live_status.facility_id
                   and a.member_id = (select auth.uid())))
  with check (exists (select 1 from public.parking_live_access a
                      where a.facility_id = parking_live_status.facility_id
                        and a.member_id = (select auth.uid())));

-- 追跡IDは1回の実行とカメラの中だけで有効な匿名ID。
-- 動画、ナンバープレート、氏名、位置情報(GPS)は保存しません。
create table if not exists public.parking_vehicle_sessions (
  session_id uuid primary key,
  facility_id text not null references public.parking_layouts(facility_id) on delete cascade,
  camera_id text not null,
  track_id integer not null,
  phase text not null check (phase in ('entering','moving','parked','exiting','exited','lost')),
  space_uid text,
  entered_at timestamptz not null,
  parked_at timestamptz,
  left_space_at timestamptz,
  exited_at timestamptz,
  last_seen_at timestamptz not null,
  position_x double precision check (position_x between 0 and 1),
  position_y double precision check (position_y between 0 and 1)
);
create index if not exists parking_vehicle_sessions_by_facility
on public.parking_vehicle_sessions (facility_id, last_seen_at desc);
alter table public.parking_vehicle_sessions enable row level security;
revoke all on public.parking_vehicle_sessions from anon, authenticated;
grant select, insert, update on public.parking_vehicle_sessions to authenticated;
create policy "vehicle sessions member read" on public.parking_vehicle_sessions
  for select to authenticated using (
    exists (select 1 from public.parking_live_access a
            where a.facility_id = parking_vehicle_sessions.facility_id
              and a.member_id = (select auth.uid()))
  );
create policy "vehicle sessions member insert" on public.parking_vehicle_sessions
  for insert to authenticated with check (
    exists (select 1 from public.parking_live_access a
            where a.facility_id = parking_vehicle_sessions.facility_id
              and a.member_id = (select auth.uid()))
  );
create policy "vehicle sessions member update" on public.parking_vehicle_sessions
  for update to authenticated
  using (exists (select 1 from public.parking_live_access a
                 where a.facility_id = parking_vehicle_sessions.facility_id
                   and a.member_id = (select auth.uid())))
  with check (exists (select 1 from public.parking_live_access a
                      where a.facility_id = parking_vehicle_sessions.facility_id
                        and a.member_id = (select auth.uid())));
