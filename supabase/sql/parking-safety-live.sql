-- Safety counts from the live camera. No person identifiers, images or tracks.
create table if not exists public.parking_safety_live (
  facility_id text not null references public.parking_layouts(facility_id) on delete cascade,
  camera_id text not null,
  pedestrian_count integer not null default 0 check (pedestrian_count between 0 and 1000),
  bicycle_count integer not null default 0 check (bicycle_count between 0 and 1000),
  pedestrian_warning boolean not null default false,
  bicycle_warning boolean not null default false,
  checked_at timestamptz not null default now(),
  primary key (facility_id, camera_id)
);
alter table public.parking_safety_live enable row level security;
grant select on public.parking_safety_live to anon, authenticated;
grant insert, update on public.parking_safety_live to authenticated;
drop policy if exists "safety published read" on public.parking_safety_live;
create policy "safety published read" on public.parking_safety_live
for select to anon, authenticated
using (exists (
  select 1 from public.parking_live_visibility v
  where v.facility_id = parking_safety_live.facility_id and v.is_published = true
));
drop policy if exists "safety members read" on public.parking_safety_live;
create policy "safety members read" on public.parking_safety_live
for select to authenticated
using (exists (
  select 1 from public.parking_live_access a
  where a.facility_id = parking_safety_live.facility_id
    and a.member_id = (select auth.uid())
));
drop policy if exists "safety members insert" on public.parking_safety_live;
create policy "safety members insert" on public.parking_safety_live
for insert to authenticated
with check (exists (
  select 1 from public.parking_live_access a
  where a.facility_id = parking_safety_live.facility_id
    and a.member_id = (select auth.uid())
));
drop policy if exists "safety members update" on public.parking_safety_live;
create policy "safety members update" on public.parking_safety_live
for update to authenticated
using (exists (
  select 1 from public.parking_live_access a
  where a.facility_id = parking_safety_live.facility_id
    and a.member_id = (select auth.uid())
))
with check (exists (
  select 1 from public.parking_live_access a
  where a.facility_id = parking_safety_live.facility_id
    and a.member_id = (select auth.uid())
));
