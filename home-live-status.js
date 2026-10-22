"use strict";
/* 自宅テスト用：YOLO満空表示。保存済み配置図の status は変更しない。 */
(() => {
  const facilityId = "home-test-001";
  const panel = document.querySelector("#home-live-status-panel");
  const notice = document.querySelector("#home-live-notice");
  const list = document.querySelector("#home-live-list");
  if (!panel || !notice || !list) return;

  let spaceNames = null;
  let busy = false;
  const labelStatus = (status) => ({
    available: "空き", occupied: "使用中", unknown: "未確認",
  }[status] || "未確認");
  const isFresh = (dateString) => {
    const ts = Date.parse(dateString ?? "");
    return Number.isFinite(ts) && Date.now() - ts >= -30000 && Date.now() - ts <= 15000;
  };
  async function getJson(path, headers) {
    const config = window.PARKING_REMOTE_CONFIG ?? {};
    const resp = await fetch(String(config.supabaseUrl ?? "").replace(/\/$/, "") + path, {
      headers, cache: "no-store", signal: AbortSignal.timeout(10000),
    });
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    return resp.json();
  }
  async function refresh() {
    if (busy || document.hidden || !panel.open) return;
    const config = window.PARKING_REMOTE_CONFIG ?? {};
    if (!config.enabled || !config.publishableKey) {
      notice.textContent = "Supabase接続設定がありません。";
      return;
    }
    let token = null;
    try { token = sessionStorage.getItem("parkingAdminRemoteToken"); } catch {}
    if (!token) {
      notice.textContent = "管理者ログイン後に最新状態を表示します。";
      list.replaceChildren();
      return;
    }
    busy = true;
    const headers = { apikey: config.publishableKey, Authorization: "Bearer " + token };
    try {
      if (!spaceNames) {
        const layouts = await getJson("/rest/v1/parking_layouts?facility_id=eq.home-test-001&select=layout_data", headers);
        const objects = layouts[0]?.layout_data?.objects ?? [];
        spaceNames = objects.filter(o => o.objectType === "parkingSpace" && o.uid)
          .map(o => ({ uid: o.uid, name: o.name || o.uid, disabled: o.status === "unavailable" }));
      }
      const rows = await getJson("/rest/v1/parking_live_status?facility_id=eq.home-test-001&select=space_uid,status,confidence,checked_at", headers);
      const data = new Map(rows.map(r => [r.space_uid, r]));
      const fragment = document.createDocumentFragment();
      let available = 0;
      let unknown = 0;
      for (const space of spaceNames) {
        const row = data.get(space.uid);
        const status = space.disabled ? "unavailable" : row && isFresh(row.checked_at) ? row.status : "unknown";
        if (status === "available") available++;
        if (status === "unknown") unknown++;
        const line = document.createElement("li");
        line.textContent = space.name + " (" + space.uid + ")："
          + (status === "unavailable" ? "利用不可" : labelStatus(status));
        fragment.append(line);
      }
      list.replaceChildren(fragment);
      notice.textContent = "自宅テスト用・YOLO判定 / 空き " + available + " / 未確認 " + unknown
        + " / " + new Date().toLocaleTimeString("ja-JP") + "確認（約3秒間隔）";
    } catch (err) {
      spaceNames = null;
      list.replaceChildren();
      notice.textContent = "取得できません（" + (err.message || "通信エラー")
        + "）。管理者ログインと読取権限を確認してください。";
    } finally {
      busy = false;
    }
  }
  panel.addEventListener("toggle", () => { if (panel.open) void refresh(); });
  document.querySelector("#cloud-login-button")?.addEventListener("click", () => {
    setTimeout(() => void refresh(), 1200);
  });
  document.querySelector("#cloud-logout-button")?.addEventListener("click", () => {
    list.replaceChildren();
    notice.textContent = "管理者ログインが必要です。";
  });
  document.querySelector("#home-live-refresh")?.addEventListener("click", () => void refresh());
  window.setInterval(() => { if (panel.open) void refresh(); }, 3000);
})();