"use strict";

/* =========================================================
   管理アプリ・ユーザーアプリ共通：クラウド同期設定

   Supabaseを使う場合だけ enabled を true にする。
   supabaseUrl と publishableKey は公開可能な接続情報として扱うが、
   書き込み権限はSupabase側のRLSと管理者ログインで制限する。

   【重要】
   service_role key / secret key は強い権限を持つ秘密情報のため、
   GitHub Pagesやブラウザーへ配信されるこのファイルには絶対に記載しない。
   ========================================================= */

window.PARKING_REMOTE_CONFIG = Object.freeze({
  /* false の間は端末保存・parking-layouts.jsだけで動作する。 */
  enabled: true,

  /* 例：https://xxxxxxxxxxxxxxxx.supabase.co */
  supabaseUrl: "https://gahoqlpuufqjqpyaaykt.supabase.co",

  /* Supabase Dashboardで確認できる公開用 publishable key / anon key。 */
  publishableKey: "sb_publishable_ZAlP-6MLZUx0-aQ_jw1btA_SxhBsPVN",
});
