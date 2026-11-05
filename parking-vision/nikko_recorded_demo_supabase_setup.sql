-- 道の駅日光の録画再生（2026-11-06）。
-- 現在の実駐車場・自宅カメラの状態や権限は変更しない。
-- 道の駅日光の現物の区画配置は未取得のため、空の編集用マップだけ作る。
-- 管理者アプリで正しい駐車区画と番号を登録してから利用者案内する。
begin;

alter table public.parking_live_status
  drop constraint if exists parking_live_status_source_check;
alter table public.parking_live_status
  add constraint parking_live_status_source_check
  check (
    source = 'yolo'
    or (source = 'recorded_video_demo'
        and facility_id in ('home-video-demo-001', 'nikko-test-001'))
  );

alter table public.parking_live_status
  drop constraint if exists parking_live_demo_phase_check;
alter table public.parking_live_status
  add constraint parking_live_demo_phase_check
  check (
    (source = 'yolo' and occupancy_phase is null)
    or (source = 'recorded_video_demo'
        and facility_id in ('home-video-demo-001', 'nikko-test-001')
        and occupancy_phase in ('available', 'parking_in', 'stopped', 'exiting', 'unknown')
        and (
          (status = 'available' and occupancy_phase = 'available')
          or (status = 'unknown' and occupancy_phase = 'unknown')
          or (status = 'occupied' and occupancy_phase in ('parking_in', 'stopped', 'exiting'))
        )
    )
  );

-- 外観や白線などの場所を推測した偽の駐車区画は作らない。
insert into public.parking_layouts (facility_id, layout_data)
values ('nikko-test-001',
        '{"schemaVersion":1,"facilityId":"nikko-test-001",
          "canvas":{"width":1800,"height":1200,"scaleMetersPerPixel":null},
          "objects":[]}'::jsonb)
on conflict (facility_id) do nothing;

-- 既存の録画実演用管理権限を持つ研究者だけに同じ権限を付与。
insert into public.parking_live_access (facility_id,member_id)
select 'nikko-test-001', member_id
from public.parking_live_access
where facility_id = 'home-video-demo-001'
on conflict (facility_id,member_id) do nothing;

-- 何も公開されていない状態から始める。実行中のみ明示してONにできる。
insert into public.parking_live_visibility (facility_id,is_published)
values ('nikko-test-001',false)
on conflict (facility_id) do nothing;

-- 録画がまだ無いので、駐車枠の状態は一件も推測登録しない。
commit;
