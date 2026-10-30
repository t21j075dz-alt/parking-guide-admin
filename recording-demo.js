"use strict";
/*
 * 管理者端末だけで録画の「駐車枠の状態.csv」を確認し、
 * 利用者アプリの録画デモページへのリンクを作成する。
 * Supabaseへは一切送信しない。現在の空き・案内情報は書き換えない。
 */
(function () {
  const STATUS_CODES = Object.freeze({ unknown: 0, available: 1, occupied: 2, blocked: 3 });
  const MAX_ROWS = 100000;
  const RECORDING_FACILITIES = Object.freeze({
    "home-test-001": "実験用駐車場（自宅駐車場リアルタイム用）",
    "home-video-demo-001": "実験用駐車場（自宅駐車場録画用）",
    "nikko-test-001": "道の駅日光",
  });

  function parseCsvLine(line) {
    const values = [];
    let text = "", quoted = false;
    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        if (quoted && line[i + 1] === '"') { text += '"'; i += 1; }
        else quoted = !quoted;
      } else if (char === "," && !quoted) {
        values.push(text); text = "";
      } else {
        text += char;
      }
    }
    if (quoted) throw new Error("CSVに閉じられていない引用符があります。");
    values.push(text);
    return values;
  }

  function buildRecordingDemo(text, facilityId = "home-test-001") {
    if (!Object.prototype.hasOwnProperty.call(RECORDING_FACILITIES, facilityId)) {
      throw new Error("録画デモは自宅駐車場または道の駅日光の実験用施設のみ対応します。");
    }
    const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(line => line.trim());
    if (lines.length < 2 || lines.length > MAX_ROWS) {
      throw new Error("CSVが空、または記録が多すぎます。");
    }
    const fields = parseCsvLine(lines[0]);
    const timeColumn = fields.indexOf("動画の時刻(秒)");
    const spaceColumn = fields.indexOf("駐車枠ID");
    const statusColumn = fields.indexOf("判定コード");
    if (timeColumn < 0 || spaceColumn < 0 || statusColumn < 0) {
      throw new Error("analyze_video.pyが出力した「駐車枠の状態.csv」を選択してください。");
    }
    const spaces = [];
    const indexByUid = new Map();
    const lastByUid = new Map();
    const events = [];
    let latestTime = -1;
    for (let rowNumber = 1; rowNumber < lines.length; rowNumber++) {
      const row = parseCsvLine(lines[rowNumber]);
      const time = Number(row[timeColumn]);
      const uid = row[spaceColumn];
      const status = row[statusColumn];
      if (!Number.isFinite(time) || time < 0 || time > 86400 ||
          typeof uid !== "string" || !/^space_[A-Za-z0-9_-]{1,40}$/.test(uid) ||
          !Object.prototype.hasOwnProperty.call(STATUS_CODES, status)) {
        throw new Error("CSVの" + (rowNumber + 1) + "行目の時刻・区画・判定に誤りがあります。");
      }
      if (time < latestTime) {
        throw new Error("CSVが時刻順に並んでいません。");
      }
      latestTime = time;
      if (!indexByUid.has(uid)) {
        if (spaces.length >= 100) throw new Error("区画が100件を超えています。");
        indexByUid.set(uid, spaces.length);
        spaces.push(uid);
      }
      if (lastByUid.get(uid) !== status) {
        events.push([time, indexByUid.get(uid), STATUS_CODES[status]]);
        lastByUid.set(uid, status);
      }
      if (events.length > 4000) {
        throw new Error("状態の変化が多すぎます。短い動画に分けて解析してください。");
      }
    }
    if (!events.length || latestTime <= 0 || !spaces.length) {
      throw new Error("解析できる駐車枠の記録がありません。");
    }
    return {
      version: 1,
      facility_id: facilityId,
      duration: latestTime,
      spaces,
      events,
    };
  }

  function setup() {
    const fileField = document.querySelector("#recording-demo-file");
    const facilityField = document.querySelector("#recording-demo-facility");
    const create = document.querySelector("#recording-demo-create");
    const link = document.querySelector("#recording-demo-link");
    const status = document.querySelector("#recording-demo-message");
    if (!fileField || !create || !link || !status) return;
    create.addEventListener("click", async () => {
      link.hidden = true;
      const file = fileField.files?.[0];
      if (!file) {
        status.textContent = "先に「駐車枠の状態.csv」を選択してください。";
        return;
      }
      if (file.size > 2000000) {
        status.textContent = "CSVが大きすぎます。2MB以下の録画に分けてください。";
        return;
      }
      create.disabled = true;
      status.textContent = "録画の状態変化を読み取っています…";
      try {
        const data = buildRecordingDemo(await file.text(), facilityField?.value ?? "home-test-001");
        const url = "https://t21j075dz-alt.github.io/parking-guide-user/recorded-demo.html#recorded=" +
          encodeURIComponent(JSON.stringify(data));
        if (url.length > 120000) {
          throw new Error("共有リンクが長すぎます。動画を短く分けてください。");
        }
        link.href = url;
        link.hidden = false;
        status.textContent = RECORDING_FACILITIES[data.facility_id] + "（過去の録画）：" + data.spaces.length +
          "区画・" + data.events.length + "件の状態変化を読み取りました。" +
          " 利用者アプリへ現在の空きとしては反映されません。";
      } catch (error) {
        status.textContent = "録画デモを作成できません：" + (error.message || "CSVを確認してください。");
      } finally {
        create.disabled = false;
      }
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { parseCsvLine, buildRecordingDemo };
  } else {
    setup();
  }
})();
