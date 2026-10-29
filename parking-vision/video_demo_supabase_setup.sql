-- 研究用「録画→YOLO→案内」の独立施設 (2026-10-29)
-- このプロジェクトのSupabaseでは既に適用済み。
-- 別環境への再現用。必ずバックアップ・アクセス権限を確認してから実行する。
-- home-test-001 の区画の現在値や公開状態には一切触れない。
--
-- 通常の物理カメラ実験: home-test-001 (source=yolo)
-- 録画の逐次解析実験: home-video-demo-001 (source=recorded_video_demo)
--
-- 「録画を現在の空き」と誤認させないため、録画施設には必ず専用IDを与える。
-- データ公開は録画プログラムが開始時だけON、終了時OFFにする。

alter table public.parking_live_status
  drop constraint if exists parking_live_status_source_check;
alter table public.parking_live_status
  add constraint parking_live_status_source_check
  check (source in ('yolo','recorded_video_demo'));

-- 管理アプリのマップ配置は同じ6区画を使用する。
-- 本番データを参照して録画専用施設に別行としてコピーする。
insert into public.parking_layouts (facility_id, layout_data)
select
  'home-video-demo-001',
  jsonb_set(layout_data, '{facilityId}', '"home-video-demo-001"'::jsonb, true)
from public.parking_layouts
where facility_id='home-test-001'
on conflict (facility_id) do nothing;

-- 登録済みの実験管理者だけが録画デモの区画を書き込める。
insert into public.parking_live_access (facility_id, member_id)
select 'home-video-demo-001', member_id
from public.parking_live_access
where facility_id='home-test-001'
on conflict do nothing;

-- ユーザーへの共有を無断では開始しない。
insert into public.parking_live_visibility (facility_id, is_published)
values ('home-video-demo-001', false)
on conflict (facility_id) do nothing;

-- 管理レイアウトを引き継いでも、既存の「空き」状態はコピーしない。
insert into public.parking_live_status
  (facility_id, space_uid, status, source, checked_at)
select 'home-video-demo-001', space_uid, 'unknown', 'recorded_video_demo', now()
from public.parking_live_status
where facility_id='home-test-001'
on conflict (facility_id, space_uid) do nothing;

-- 既存のRLSポリシー（parking_live_accessの管理者だけが更新可能、
-- is_published=trueの施設だけがanon read可能）を再利用する。
-- service_roleのブラウザーへの埋め込みやRLSの無効化は不要。
