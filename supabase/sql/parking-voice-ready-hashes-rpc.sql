-- 2026-10-30 本番Supabaseへ適用済み。
-- 公開済み音声のハッシュのみ返す。PostgREST単一取得の1000行上限を回避。
-- 個別の施設名、店舗名、管理者・音声生成ジョブの内容は公開しない。
create or replace function public.parking_voice_ready_hashes()
returns text[]
language sql stable security invoker set search_path = ''
as $$
  select coalesce(array_agg(r.audio_hash order by r.audio_hash), array[]::text[])
  from public.parking_voice_ready r
$$;
revoke all on function public.parking_voice_ready_hashes() from public;
grant execute on function public.parking_voice_ready_hashes() to anon, authenticated, service_role;
-- 動作確認: select cardinality(public.parking_voice_ready_hashes());
