-- Apply separately in Supabase SQL Editor. No production changes are automatic.
-- Use the same explicit operator accounts as the existing management application.
-- IMPORTANT: authenticated is NOT an administrator role. Operators must be allowlisted.
create table if not exists public.parking_camera_operators (
  user_id uuid primary key references auth.users(id) on delete cascade
);
alter table public.parking_camera_operators enable row level security;
revoke all on public.parking_camera_operators from anon, authenticated;
create or replace function public.is_parking_camera_operator() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.parking_camera_operators where user_id = auth.uid());
$$;
revoke all on function public.is_parking_camera_operator() from public;
grant execute on function public.is_parking_camera_operator() to anon, authenticated;
create table if not exists public.parking_camera_private (
  facility_id text not null, camera_id text not null,
  captured_at timestamptz not null,
  image_data text not null check (length(image_data) <= 2800000 and image_data like 'data:image/jpeg;base64,%'),
  primary key (facility_id, camera_id)
);
create table if not exists public.parking_camera_public (
  like public.parking_camera_private including all,
  is_published boolean not null default false
);
alter table public.parking_camera_private enable row level security;
alter table public.parking_camera_public enable row level security;
revoke all on public.parking_camera_private, public.parking_camera_public from anon, authenticated;
grant select, insert, update, delete on public.parking_camera_private, public.parking_camera_public to authenticated;
grant select on public.parking_camera_public to anon;
drop policy if exists camera_private_operator on public.parking_camera_private;
create policy camera_private_operator on public.parking_camera_private for all to authenticated
using (public.is_parking_camera_operator()) with check (public.is_parking_camera_operator());
drop policy if exists camera_public_operator on public.parking_camera_public;
create policy camera_public_operator on public.parking_camera_public for all to authenticated
using (public.is_parking_camera_operator()) with check (public.is_parking_camera_operator());
drop policy if exists camera_public_view on public.parking_camera_public;
create policy camera_public_view on public.parking_camera_public for select to anon, authenticated
using (is_published and captured_at > now() - interval '6 minutes' and captured_at <= now() + interval '5 seconds');
-- Provision an operator ONLY from trusted SQL Editor, using the actual auth.users UUID:
-- insert into public.parking_camera_operators(user_id) values ('operator-uuid');
-- To revoke public access immediately, set is_published=false or delete the public row.
