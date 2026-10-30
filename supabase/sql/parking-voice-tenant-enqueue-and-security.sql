-- Supabase SQL source record, deployed on 2026-10-30.
-- User app can read layouts but only registered operators may edit them.
-- A successful layout INSERT / UPDATE automatically queues its tenant names.
create schema if not exists private;
revoke all on schema private from public,anon;
grant usage on schema private to authenticated;

create or replace function private.parking_is_operator()
returns boolean
language sql stable security definer set search_path = ''
as $$
  select exists(select 1 from public.parking_camera_operators p
    where p.user_id = (select auth.uid()))
$$;
revoke all on function private.parking_is_operator() from public,anon;
grant execute on function private.parking_is_operator() to authenticated;

drop policy if exists "parking layouts authenticated insert" on public.parking_layouts;
drop policy if exists "parking layouts authenticated update" on public.parking_layouts;
drop policy if exists "parking layouts authenticated delete" on public.parking_layouts;
create policy "parking layouts authenticated insert"
 on public.parking_layouts for insert to authenticated
 with check ((select private.parking_is_operator()));
create policy "parking layouts authenticated update"
 on public.parking_layouts for update to authenticated
 using ((select private.parking_is_operator()))
 with check ((select private.parking_is_operator()));
create policy "parking layouts authenticated delete"
 on public.parking_layouts for delete to authenticated
 using ((select private.parking_is_operator()));

create or replace function private.parking_queue_tenant_voice()
returns trigger
language plpgsql security definer set search_path = ''
as $$
declare tenant jsonb; spoken text; name_hash text;
begin
  if jsonb_typeof(new.layout_data->'destinations') <> 'array' then return new; end if;
  if jsonb_array_length(new.layout_data->'destinations') > 100 then
    raise exception 'Too many destinations for a single parking layout';
  end if;
  for tenant in select value from jsonb_array_elements(new.layout_data->'destinations')
  loop
    if jsonb_typeof(tenant) <> 'object' then continue; end if;
    spoken := trim(coalesce(nullif(trim(tenant->>'nameReading'), ''),tenant->>'name', ''));
    if char_length(spoken) < 1 or char_length(spoken) > 160 then continue; end if;
    name_hash := encode(extensions.digest(
      convert_to('voice-cache-v1:8:'||spoken,'UTF8'),'sha256'),'hex');
    insert into public.parking_voice_jobs(audio_hash,spoken_text,source_type)
      values(name_hash,spoken,'tenant')
    on conflict(audio_hash) do nothing;
  end loop;
  return new;
end;
$$;
revoke all on function private.parking_queue_tenant_voice() from public,anon,authenticated;
drop trigger if exists parking_queue_tenant_voice on public.parking_layouts;
create trigger parking_queue_tenant_voice
 after insert or update of layout_data on public.parking_layouts
 for each row execute function private.parking_queue_tenant_voice();

-- One-time backfill: safe to re-run because the audio hash is the primary key.
insert into public.parking_voice_jobs(audio_hash,spoken_text,source_type)
select distinct on (audio_hash) audio_hash,spoken,'tenant'
from (
  select trim(coalesce(nullif(trim(t.value->>'nameReading'), ''),t.value->>'name','')) as spoken,
    encode(extensions.digest(convert_to('voice-cache-v1:8:'||
      trim(coalesce(nullif(trim(t.value->>'nameReading'), ''),t.value->>'name','')),
      'UTF8'),'sha256'),'hex') as audio_hash
  from public.parking_layouts l
  cross join lateral jsonb_array_elements(
    case when jsonb_typeof(l.layout_data->'destinations')='array'
      then l.layout_data->'destinations' else '[]'::jsonb end) t(value)
) names
where char_length(spoken) between 1 and 160
order by audio_hash
on conflict(audio_hash) do nothing;
