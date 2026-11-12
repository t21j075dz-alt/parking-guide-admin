"use strict";
/**
 * 店舗の交通注意事項。確認済みの情報だけ利用者に公開する。
 * レイアウトの安全設定は既存の端末保存・クラウド同期経路を使用する。
 */
(() => {
  const host = document.querySelector("#camera-monitor");
  if (!host) return;
  const types = [
    ["right_turn_prohibited", "右折入場禁止", "この駐車場は右折で入場できません。現地の標識に従ってください。"],
    ["uturn_prohibited_ahead", "周辺のUターン禁止", "施設周辺にはUターン禁止区間があります。無理な方向転換をせず、現地標識に従ってください。"],
    ["exit_only_next_entrance", "出口の先に入口あり", "手前は出口専用です。その先の入口をご利用ください。"],
    ["entrance_only", "入口専用", "こちらは入口専用です。出口とお間違えのないようご注意ください。"],
    ["custom", "その他の注意", ""],
  ];
  const panel = document.createElement("dialog");
  panel.className = "camera-card facility-dialog";
  panel.setAttribute("aria-label", "交通・安全案内");
  panel.innerHTML = '<h2>交通・安全案内</h2><p>現地で確認した交通ルールや入口案内を登録します。標識や道路状況が未確認の内容は利用者に公開しません。</p>' +
    '<label>対象<select id="traffic-scope"><option value="">施設全体</option></select></label>' +
    '<label>登録済みの注意事項<select id="traffic-existing"><option value="">新しく追加</option></select></label>' +
    '<label>注意の種類<select id="traffic-type"></select></label>' +
    '<label>案内するタイミング<select id="traffic-stage"><option value="approach">施設に近づくとき</option><option value="onsite">駐車場内</option></select></label>' +
    '<label>画面表示・読み上げ文<textarea id="traffic-message" maxlength="160" rows="3" placeholder="短く、運転中にもわかる文章"></textarea></label>' +
    '<label><input type="checkbox" id="traffic-verified"> 現地の標識・店舗案内を確認済み（利用者に公開）</label>' +
    '<label><input type="checkbox" id="traffic-enabled" checked> この注意事項を有効にする</label>' +
    '<p>登録内容は音声生成待ちにも追加されます。未確認の内容は利用者アプリへ表示・読み上げしません。</p>' +
    '<div class="dialog-actions"><button id="traffic-save" type="button">保存する</button><button id="traffic-delete" type="button">選択項目を削除</button><button id="traffic-close" type="button">閉じる</button></div>' +
    '<p id="traffic-editor-status" role="status" aria-live="polite"></p>' +
    '<hr><h3>カメラによる安全警告</h3><p>歩行者・自転車の警告はカメラ処理で判定します。検出数が継続して基準を超え、最新の情報がある場合だけ案内します。画像・個人を識別するIDは利用者に公開しません。</p>';
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.textContent = "交通・安全案内";
  host.after(trigger);
  document.body.append(panel);
  const q = id => panel.querySelector("#" + id);
  const typeInput = q("traffic-type");
  for (const [id, label] of types) typeInput.add(new Option(label, id));
  let activeLayout = null;

  function destinations(layout) {
    return Array.isArray(layout?.destinations) ? layout.destinations : getAdminDestinations();
  }
  function records() {
    return Array.isArray(activeLayout?.safetyAdvisories) ? activeLayout.safetyAdvisories : [];
  }
  function resetForm() {
    q("traffic-existing").value = "";
    typeInput.value = "right_turn_prohibited";
    q("traffic-stage").value = "approach";
    q("traffic-message").value = types[0][2];
    q("traffic-verified").checked = false;
    q("traffic-enabled").checked = true;
    q("traffic-delete").disabled = true;
  }
  function updateOptions(selected = "") {
    q("traffic-existing").replaceChildren(new Option("新しく追加", ""));
    for (const record of records()) {
      const label = types.find(item => item[0] === record.type)?.[1] || "個別の注意";
      const prefix = record.destinationId ? "店舗別：" : "施設全体：";
      q("traffic-existing").add(new Option(prefix + label, record.id));
    }
    q("traffic-existing").value = records().some(item => item.id === selected) ? selected : "";
  }
  function loadRecord() {
    const item = records().find(record => record.id === q("traffic-existing").value);
    if (!item) { resetForm(); return; }
    typeInput.value = types.some(type => type[0] === item.type) ? item.type : "custom";
    q("traffic-scope").value = item.destinationId || "";
    q("traffic-stage").value = item.stage === "onsite" ? "onsite" : "approach";
    q("traffic-message").value = item.message || "";
    q("traffic-verified").checked = item.verified === true;
    q("traffic-enabled").checked = item.enabled === true;
    q("traffic-delete").disabled = false;
  }
  function load() {
    activeLayout = getCurrentLayout();
    q("traffic-scope").replaceChildren(new Option("施設全体", ""));
    for (const item of destinations(activeLayout)) {
      if (item?.id && item?.name) q("traffic-scope").add(new Option(item.name, item.id));
    }
    updateOptions();
    resetForm();
    q("traffic-editor-status").textContent = "";
  }
  trigger.addEventListener("click", () => { load(); panel.showModal(); });
  q("traffic-close").onclick = () => panel.close();
  q("traffic-existing").onchange = loadRecord;
  typeInput.onchange = () => {
    const item = types.find(type => type[0] === typeInput.value);
    if (item && item[0] !== "custom") q("traffic-message").value = item[2];
  };
  q("traffic-save").onclick = () => {
    const layout = getCurrentLayout();
    if (!layout || layout !== activeLayout) {
      q("traffic-editor-status").textContent = "施設が変更されました。開き直してください。";
      return;
    }
    const message = q("traffic-message").value.trim();
    if (!message || message.length > 160) {
      q("traffic-editor-status").textContent = "読み上げ文を1～160文字で入力してください。";
      return;
    }
    const selected = q("traffic-existing").value;
    const list = records().slice();
    const id = selected || "traffic-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
    const record = {
      id, type: typeInput.value, message, stage: q("traffic-stage").value,
      destinationId: q("traffic-scope").value || "",
      verified: q("traffic-verified").checked,
      enabled: q("traffic-enabled").checked,
    };
    const index = list.findIndex(item => item.id === id);
    if (index < 0) list.push(record); else list[index] = record;
    layout.safetyAdvisories = list;
    saveLocal();
    updateOptions(id);
    q("traffic-editor-status").textContent = record.verified
      ? "保存しました。ログイン中はクラウドへ自動反映されます。"
      : "保存しました。未確認のため利用者には公開しません。";
  };
  q("traffic-delete").onclick = () => {
    const id = q("traffic-existing").value;
    if (!id || getCurrentLayout() !== activeLayout) return;
    activeLayout.safetyAdvisories = records().filter(item => item.id !== id);
    saveLocal();
    updateOptions();
    resetForm();
    q("traffic-editor-status").textContent = "削除しました。";
  };
})();