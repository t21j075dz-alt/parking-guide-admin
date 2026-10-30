-- Queue priority as deployed in Supabase on 2026-10-30.
-- 1. Newly registered tenant/store names
-- 2. Shared fixed phrases used by all facilities
-- 3. Existing facility names
-- Never claim an unfinished job before its cooldown expires.
create or replace function public.parking_voice_claim_job()
returns table(audio_hash text, spoken_text text, attempts integer)
language plpgsql security definer set search_path = ''
as $$
begin
  return query
  with chosen as (
    select j.audio_hash
    from public.parking_voice_jobs j
    where (j.status in ('pending','retry') and j.next_attempt_at <= now())
       or (j.status='processing' and j.updated_at < now() - interval '10 minutes')
    order by
      case j.source_type
        when 'tenant' then 0
        when 'other' then 1
        when 'facility' then 2
        else 3
      end,
      j.next_attempt_at, j.created_at
    for update skip locked limit 1
  ), taken as (
    update public.parking_voice_jobs j
    set status='processing',
        attempts=j.attempts+1,
        updated_at=now()
    from chosen
    where j.audio_hash=chosen.audio_hash
    returning j.audio_hash,j.spoken_text,j.attempts
  )
  select t.audio_hash,t.spoken_text,t.attempts from taken t;
end;
$$;
revoke all on function public.parking_voice_claim_job() from public,anon,authenticated;
grant execute on function public.parking_voice_claim_job() to service_role;
