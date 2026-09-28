-- ============================================================
-- 駐車場マップ自動反映用 Supabase 初期設定
--
-- 実行場所：
-- Supabase Dashboard > SQL Editor
--
-- 方針：
-- 1. 利用者アプリ（anon）はレイアウトを読むだけ。
-- 2. 管理アプリはSupabase Authでログインした authenticated のみ書込可能。
-- 3. ブラウザーへ service_role / secret key は配布しない。
-- ============================================================

-- 施設ごとに1行の最新レイアウトを保持する。
create table if not exists public.parking_layouts (
  facility_id text primary key,
  layout_data jsonb not null,
  updated_at timestamptz not null default now()
);

-- Row Level Securityを有効化し、誰が何をできるかをポリシーで限定する。
alter table public.parking_layouts enable row level security;

-- 既定権限を明示的に整理する。
revoke all on table public.parking_layouts from anon, authenticated;

-- 利用者アプリは匿名読取、管理者はログイン後に読取・更新できる。
grant select on table public.parking_layouts to anon, authenticated;
grant insert, update, delete on table public.parking_layouts to authenticated;

-- 利用者アプリと管理アプリの双方がレイアウトを取得できる読取ポリシー。
drop policy if exists "parking layouts public read" on public.parking_layouts;
create policy "parking layouts public read"
on public.parking_layouts
for select
to anon, authenticated
using (true);

-- 管理者ログイン済みユーザーだけが新しい施設レイアウトを登録できる。
drop policy if exists "parking layouts authenticated insert" on public.parking_layouts;
create policy "parking layouts authenticated insert"
on public.parking_layouts
for insert
to authenticated
with check (true);

-- 管理者ログイン済みユーザーだけが既存レイアウトを更新できる。
drop policy if exists "parking layouts authenticated update" on public.parking_layouts;
create policy "parking layouts authenticated update"
on public.parking_layouts
for update
to authenticated
using (true)
with check (true);

-- 管理者ログイン済みユーザーだけが不要レイアウトを削除できる。
drop policy if exists "parking layouts authenticated delete" on public.parking_layouts;
create policy "parking layouts authenticated delete"
on public.parking_layouts
for delete
to authenticated
using (true);
