"use strict";
/**
 * 管理アプリ：店舗登録・変更に合わせて読み上げ名をサーバー側へ登録する。
 * - 端末では音声を生成しない。TTSエラーや429を管理画面操作から分離する。
 * - Supabase Edge Function側で管理者ログインを検証する。
 * - 同じ名前はハッシュが同じため何度送っても一度だけ生成される。
 */
window.ParkingAdminVoice = (() => {
  const endpoint = "/functions/v1/parking-voice-prepare";
  const seen = new Map();
  let statusText = null;
  let active = false;

  function setup() {
    if (document.querySelector("#admin-voice-queue-panel")) return;
    const host = document.querySelector("#cloud-sync-status");
    if (!host) return;
    const panel = document.createElement("section");
    panel.id = "admin-voice-queue-panel";
    panel.className = "camera-card";
    const title = document.createElement("h3");
    title.textContent = "施設名・店舗名の音声準備";
    statusText = document.createElement("p");
    statusText.id = "admin-voice-queue-status";
    statusText.setAttribute("role", "status");
    statusText.textContent = "管理者ログイン後、登録済み施設名の生成待ちを自動登録します。";
    const info = document.createElement("p");
    info.className = "muted";
    info.textContent = "店舗の追加や名前の変更をクラウドへ保存すると、音声も自動で生成待ちに入ります。完了までの状態を確認できます。";
    const row = document.createElement("div");
    row.className = "object-actions";
    const requeue = document.createElement("button");
    requeue.type = "button";
    requeue.textContent = "既存の施設・店舗名をまとめて登録";
    requeue.id = "admin-voice-backfill";
    const refresh = document.createElement("button");
    refresh.type = "button";
    refresh.textContent = "音声の準備状況を更新";
    refresh.id = "admin-voice-refresh";
    row.append(requeue, refresh);
    panel.append(title, statusText, info, row);
    host.after(panel);
    requeue.addEventListener("click", () => window.ParkingAdminVoice.requestBackfill?.());
    refresh.addEventListener("click", () => window.ParkingAdminVoice.requestStatus?.());
  }
  function say(message) {
    if (!statusText) setup();
    if (statusText) statusText.textContent = message;
  }
  function speechName(facility) {
    const value = facility?.nameReading || window.PARKING_SPEECH_READINGS?.[facility?.id]
      || facility?.displayName || facility?.name || "";
    return typeof normalizeJapaneseSpeech === "function"
      ? normalizeJapaneseSpeech(String(value).trim()) : String(value).trim();
  }
  function destinationNames(layout) {
    return (Array.isArray(layout?.destinations) ? layout.destinations : [])
      .map(x => ({
        text: typeof normalizeJapaneseSpeech === "function"
          ? normalizeJapaneseSpeech(x?.nameReading || x?.name || "") : (x?.nameReading || x?.name || ""),
        type: "tenant",
      })).filter(x => String(x.text).trim());
  }
  function itemsForFacility(facility, layout) {
    const list = [];
    const name = speechName(facility);
    if (name) list.push({ text: name, type: "facility" });
    list.push(...destinationNames(layout));
    return list;
  }
  function itemsForCatalog(facilities, layouts) {
    const all = [];
    for (const f of facilities || []) all.push(...itemsForFacility(f,layouts?.[f.id]));
    for (const [id, layout] of Object.entries(layouts || {})) {
      if (!(facilities || []).some(f => f.id === id)) all.push(...destinationNames(layout));
    }
    return [...new Map(all.map(x => [x.text, x])).values()];
  }
  async function call(action, config, token, items) {
    if (!token || !config?.enabled) return { error: "管理者ログインが必要です" };
    try {
      const response = await fetch(config.url + endpoint, {
        method: "POST",
        headers: { apikey: config.publishableKey, Authorization: "Bearer " + token,
          "Content-Type": "application/json" },
        body: JSON.stringify({ action, ...(items ? { items } : {}) }),
        signal: AbortSignal.timeout(30000),
      });
      const payload = await response.json().catch(() => ({}));
      return response.ok ? payload : { error: payload.error || "音声サーバーが応答しません" };
    } catch {
      return { error: "音声生成の登録先に接続できません。後から再試行できます。" };
    }
  }
  async function queueLayout(facility, layout, config, token) {
    const items = itemsForFacility(facility, layout);
    if (!items.length) return;
    const signature = JSON.stringify(items);
    if (seen.get(facility?.id) === signature) return;
    const result = await call("enqueue", config, token, items);
    if (result.error) {
      say("施設データは保存しましたが、音声登録は未完了：" + result.error);
      return;
    }
    seen.set(facility?.id, signature);
    say("施設・店舗の音声を生成待ちに登録しました（" + result.accepted + "件）。音声の保存完了は「準備状況を更新」で確認できます。");
  }
  async function queueCatalog(facilities, layouts, config, token) {
    if (active) return;
    active = true;
    try {
      const all = itemsForCatalog(facilities, layouts);
      let total = 0;
      for (let start = 0; start < all.length; start += 200) {
        const result = await call("enqueue", config, token, all.slice(start, start + 200));
        if (result.error) { say("音声登録が中断しました：" + result.error); return; }
        total += result.accepted;
        say("施設・店舗名の生成待ち登録：" + Math.min(start + 200, all.length) + "/" + all.length + " 件");
      }
      say("登録済みの施設・店舗名を生成待ちに登録しました（" + total + "件）。自動で順番に音声を生成します。");
    } finally { active = false; }
  }
  async function refresh(config, token) {
    const result = await call("status", config, token);
    if (result.error) { say(result.error); return; }
    const t = result.totals || {};
    say("保存完了 " + (t.ready || 0) + " 件／未生成 " + (t.pending || 0)
      + " 件／生成中 " + (t.processing || 0) + " 件／再試行待ち " + (t.retry || 0)
      + " 件／生成失敗 " + (t.failed || 0) + " 件");
  }
  return Object.freeze({ setup, queueLayout, queueCatalog, refresh, itemsForFacility, itemsForCatalog });
})();
