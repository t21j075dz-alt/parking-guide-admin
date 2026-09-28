"use strict";

/* =========================================================
   駐車場マップ管理：状態と定義
   ========================================================= */

const ENTRANCE_LABELS = {
  main: "正面入口",
  sub: "その他の一般入口",
  accessible: "バリアフリー入口",
  staff: "従業員入口",
  other: "その他",
};

const OBJECT_DEFAULTS = {
  parkingSpace: { width: 70, height: 130, name: "駐車区画" },
  road: { width: 260, height: 90, name: "車道" },
  sidewalk: { width: 260, height: 45, name: "歩道" },
  crosswalk: { width: 110, height: 45, name: "横断歩道" },
  building: { width: 260, height: 160, name: "建物" },
  buildingEntrance: { width: 34, height: 34, name: "店舗入口" },
  parkingEntrance: { width: 42, height: 42, name: "駐車場出入口" },
  stopLine: { width: 110, height: 14, name: "停止線" },
  speedBump: { width: 110, height: 22, name: "速度抑制ハンプ" },
  noEntry: { width: 42, height: 42, name: "進入禁止" },
  cartCorral: { width: 120, height: 80, name: "カート置き場" },
  bicycleParking: { width: 150, height: 80, name: "駐輪場" },
  motorcycleParking: { width: 110, height: 80, name: "二輪車置場" },
  loadingZone: { width: 180, height: 100, name: "荷捌きスペース" },
  evCharger: { width: 42, height: 42, name: "EV充電器" },
};

const state = {
  facilities: window.ADMIN_FACILITY_CATALOG?.facilities ?? [],
  layouts: {},
  facilityId: null,
  selectedUid: null,
  drag: null,
};

const elements = {
  prefectureSelect: document.querySelector("#prefecture-select"),
  facilitySelect: document.querySelector("#facility-select"),
  facilityId: document.querySelector("#facility-id"),
  canvas: document.querySelector("#map-canvas"),
  canvasWidth: document.querySelector("#canvas-width"),
  canvasHeight: document.querySelector("#canvas-height"),
  canvasScale: document.querySelector("#canvas-scale"),
  emptySettings: document.querySelector("#empty-settings"),
  form: document.querySelector("#object-form"),
  uid: document.querySelector("#object-uid"),
  type: document.querySelector("#object-type"),
  name: document.querySelector("#object-name"),
  x: document.querySelector("#object-x"),
  y: document.querySelector("#object-y"),
  rotation: document.querySelector("#object-rotation"),
  width: document.querySelector("#object-width"),
  height: document.querySelector("#object-height"),
  widthField: document.querySelector("#width-field"),
  heightField: document.querySelector("#height-field"),
  parkingSpaceSettings: document.querySelector("#parking-space-settings"),
  spaceType: document.querySelector("#space-type"),
  spaceStatus: document.querySelector("#space-status"),
  roadSettings: document.querySelector("#road-settings"),
  roadDirection: document.querySelector("#road-direction"),
  parkingEntranceSettings: document.querySelector("#parking-entrance-settings"),
  parkingAccessType: document.querySelector("#parking-access-type"),
  buildingEntranceSettings: document.querySelector("#building-entrance-settings"),
  entranceType: document.querySelector("#entrance-type"),
  publicAccess: document.querySelector("#public-access"),
  wheelchairAccessible: document.querySelector("#wheelchair-accessible"),
  guideTarget: document.querySelector("#guide-target"),
  buildingId: document.querySelector("#building-id"),
  themeButton: document.querySelector("#theme-button"),
};

/* =========================================================
   レイアウトの生成・取得
   ========================================================= */

function getCurrentLayout() {
  return state.layouts[state.facilityId] ?? null;
}

function ensureLayout(facilityId) {
  if (!state.layouts[facilityId]) {
    state.layouts[facilityId] = {
      schemaVersion: 1,
      facilityId,
      canvas: { width: 1000, height: 700, scaleMetersPerPixel: null },
      objects: [],
    };
  }
  return state.layouts[facilityId];
}

function getSelectedObject() {
  return getCurrentLayout()?.objects.find((item) => item.uid === state.selectedUid) ?? null;
}

function createUid(type) {
  const prefix = {
    parkingSpace: "space",
    road: "road",
    sidewalk: "sidewalk",
    crosswalk: "crosswalk",
    building: "building",
    buildingEntrance: "entrance",
      parkingEntrance: "parking_entrance",
    stopLine: "stop_line",
    speedBump: "speed_bump",
    noEntry: "no_entry",
    cartCorral: "cart",
    bicycleParking: "bicycle",
    motorcycleParking: "motorcycle",
    loadingZone: "loading",
    evCharger: "ev_charger",
  }[type] ?? "object";
  const used = new Set(getCurrentLayout()?.objects.map((item) => item.uid) ?? []);
  let number = 1;
  while (used.has(`${prefix}_${String(number).padStart(3, "0")}`)) {
    number += 1;
  }
  return `${prefix}_${String(number).padStart(3, "0")}`;
}

function addObject(type, options = {}) {
  const layout = ensureLayout(state.facilityId);
  const defaults = OBJECT_DEFAULTS[type];
  if (!defaults) {
    return;
  }
  const uid = createUid(type);
  const item = {
    uid,
    objectType: type,
    name: defaults.name,
    x: Math.round(layout.canvas.width / 2 - defaults.width / 2),
    y: Math.round(layout.canvas.height / 2 - defaults.height / 2),
    width: defaults.width,
    height: defaults.height,
    rotation: 0,
  };
  if (type === "parkingSpace") {
    item.spaceType = options.spaceType ?? "standard";
    item.status = "available";
    item.name = `${item.spaceType === "compact" ? "軽" : item.spaceType === "accessible" ? "車椅子" : item.spaceType === "ev" ? "EV" : "普通車"} ${uid.replace("space_", "")}`;
  }
  if (type === "road") {
    item.trafficDirection = options.trafficDirection ?? "twoWay";
    item.name = item.trafficDirection === "oneWay" ? "一方通行" : "車道";
  }
  if (type === "parkingEntrance") {
    item.accessType = options.accessType ?? "both";
    item.name = item.accessType === "entrance"
      ? "駐車場入口"
      : item.accessType === "exit"
        ? "駐車場出口"
        : "駐車場出入口";
  }
  if (type === "buildingEntrance") {
    Object.assign(item, {
      entranceType: "main",
      publicAccess: true,
      wheelchairAccessible: false,
      guideTarget: true,
      buildingId: "",
    });
  }
  layout.objects.push(item);
  state.selectedUid = uid;
  saveLocal();
  render();
}

/* =========================================================
   描画・選択・ドラッグ
   ========================================================= */

function render() {
  const layout = ensureLayout(state.facilityId);
  elements.canvas.style.width = `${layout.canvas.width}px`;
  elements.canvas.style.height = `${layout.canvas.height}px`;
  elements.canvasWidth.value = layout.canvas.width;
  elements.canvasHeight.value = layout.canvas.height;
  elements.canvasScale.value = layout.canvas.scaleMetersPerPixel ?? "";
  elements.canvas.replaceChildren();

  layout.objects.forEach((item) => {
    const node = document.createElement("div");
    node.className = "map-object";
    node.dataset.uid = item.uid;
    node.dataset.objectType = item.objectType;
    if (item.objectType === "road") {
      node.dataset.trafficDirection = item.trafficDirection ?? "twoWay";
    }
    if (item.objectType === "parkingEntrance") {
      node.dataset.accessType = item.accessType ?? "both";
    }
    node.style.left = `${item.x}px`;
    node.style.top = `${item.y}px`;
    node.style.width = `${item.width ?? 34}px`;
    node.style.height = `${item.height ?? 34}px`;
    node.style.transform = `rotate(${item.rotation ?? 0}deg)`;
    node.classList.toggle("selected", item.uid === state.selectedUid);
    const label = document.createElement("span");
    label.textContent = item.name || item.uid;
    node.append(label);
    node.addEventListener("pointerdown", startDrag);
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      selectObject(item.uid);
    });
    elements.canvas.append(node);
  });
  updateSettings();
}

function selectObject(uid) {
  state.selectedUid = uid;
  render();
}

function startDrag(event) {
  if (event.button !== 0) {
    return;
  }
  const item = getCurrentLayout().objects.find((object) => object.uid === event.currentTarget.dataset.uid);
  if (!item) {
    return;
  }
  state.selectedUid = item.uid;
  state.drag = {
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startX: item.x,
    startY: item.y,
  };
  event.currentTarget.setPointerCapture(event.pointerId);
  event.preventDefault();
  elements.canvas.querySelectorAll(".map-object").forEach((node) => {
    node.classList.toggle("selected", node.dataset.uid === item.uid);
  });
  updateSettings();
}

function moveDrag(event) {
  if (!state.drag || event.pointerId !== state.drag.pointerId) {
    return;
  }
  const item = getSelectedObject();
  const layout = getCurrentLayout();
  if (!item || !layout) {
    return;
  }
  item.x = Math.round(Math.max(0, Math.min(layout.canvas.width - (item.width ?? 34), state.drag.startX + event.clientX - state.drag.startClientX)));
  item.y = Math.round(Math.max(0, Math.min(layout.canvas.height - (item.height ?? 34), state.drag.startY + event.clientY - state.drag.startClientY)));
  const node = elements.canvas.querySelector(`[data-uid="${CSS.escape(item.uid)}"]`);
  if (node) {
    node.style.left = `${item.x}px`;
    node.style.top = `${item.y}px`;
  }
  elements.x.value = item.x;
  elements.y.value = item.y;
}

function endDrag(event) {
  if (!state.drag || event.pointerId !== state.drag.pointerId) {
    return;
  }
  state.drag = null;
  saveLocal();
}

/* =========================================================
   右側設定パネル
   ========================================================= */

function updateSettings() {
  const item = getSelectedObject();
  elements.emptySettings.hidden = Boolean(item);
  elements.form.hidden = !item;
  if (!item) {
    return;
  }
  elements.uid.value = item.uid;
  elements.type.value = item.objectType;
  elements.name.value = item.name ?? "";
  elements.x.value = item.x ?? 0;
  elements.y.value = item.y ?? 0;
  elements.rotation.value = item.rotation ?? 0;
  elements.width.value = item.width ?? 34;
  elements.height.value = item.height ?? 34;
  const fixedMarker = ["buildingEntrance", "parkingEntrance", "noEntry", "evCharger"].includes(item.objectType);
  elements.widthField.hidden = fixedMarker;
  elements.heightField.hidden = fixedMarker;

  elements.roadSettings.hidden = item.objectType !== "road";
  if (item.objectType === "road") {
    elements.roadDirection.value = item.trafficDirection ?? "twoWay";
  }

  elements.parkingEntranceSettings.hidden = item.objectType !== "parkingEntrance";
  if (item.objectType === "parkingEntrance") {
    elements.parkingAccessType.value = item.accessType ?? "both";
  }

  elements.parkingSpaceSettings.hidden = item.objectType !== "parkingSpace";
  if (item.objectType === "parkingSpace") {
    elements.spaceType.value = item.spaceType ?? "standard";
    elements.spaceStatus.value = item.status ?? "available";
  }

  elements.buildingEntranceSettings.hidden = item.objectType !== "buildingEntrance";
  if (item.objectType === "buildingEntrance") {
    elements.entranceType.value = item.entranceType ?? "main";
    elements.publicAccess.checked = item.publicAccess !== false;
    elements.wheelchairAccessible.checked = item.wheelchairAccessible === true;
    elements.guideTarget.checked = item.guideTarget === true;
    elements.buildingId.value = item.buildingId ?? "";
  }
}

function updateSelectedFromForm() {
  const item = getSelectedObject();
  const layout = getCurrentLayout();
  if (!item || !layout) {
    return;
  }
  item.name = elements.name.value.trim() || item.uid;
  item.x = Math.max(0, Number(elements.x.value) || 0);
  item.y = Math.max(0, Number(elements.y.value) || 0);
  item.rotation = Number(elements.rotation.value) || 0;
  if (!["buildingEntrance", "parkingEntrance", "noEntry", "evCharger"].includes(item.objectType)) {
    item.width = Math.max(8, Number(elements.width.value) || 8);
    item.height = Math.max(8, Number(elements.height.value) || 8);
  }
  if (item.objectType === "road") {
    item.trafficDirection = elements.roadDirection.value;
  }
  if (item.objectType === "parkingEntrance") {
    item.accessType = elements.parkingAccessType.value;
  }
  if (item.objectType === "parkingSpace") {
    item.spaceType = elements.spaceType.value;
    item.status = elements.spaceStatus.value;
  }
  if (item.objectType === "buildingEntrance") {
    item.entranceType = elements.entranceType.value;
    item.publicAccess = elements.publicAccess.checked;
    item.wheelchairAccessible = elements.wheelchairAccessible.checked;
    item.guideTarget = elements.guideTarget.checked;
    item.buildingId = elements.buildingId.value.trim();
  }
  item.x = Math.min(item.x, layout.canvas.width - (item.width ?? 34));
  item.y = Math.min(item.y, layout.canvas.height - (item.height ?? 34));
  saveLocal();
  render();
}

function duplicateSelected() {
  const item = getSelectedObject();
  if (!item) {
    return;
  }
  const copy = structuredClone(item);
  copy.uid = createUid(item.objectType);
  copy.name = `${item.name} コピー`;
  copy.x += 20;
  copy.y += 20;
  getCurrentLayout().objects.push(copy);
  state.selectedUid = copy.uid;
  saveLocal();
  render();
}

function deleteSelected() {
  const layout = getCurrentLayout();
  if (!layout || !state.selectedUid) {
    return;
  }
  layout.objects = layout.objects.filter((item) => item.uid !== state.selectedUid);
  state.selectedUid = null;
  saveLocal();
  render();
}

/* =========================================================
   保存・入出力
   ========================================================= */

function saveLocal() {
  try {
    localStorage.setItem("parkingAdminLayoutsV1", JSON.stringify(state.layouts));
  } catch {
    /* 保存できない環境でも編集は継続する。 */
  }
}

function restoreLocal() {
  try {
    const saved = JSON.parse(localStorage.getItem("parkingAdminLayoutsV1") ?? "null");
    if (saved && typeof saved === "object") {
      state.layouts = saved;
    }
  } catch {
    state.layouts = {};
  }
}

function downloadText(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function exportJson() {
  downloadText("parking-layouts.json", `${JSON.stringify(state.layouts, null, 2)}\n`, "application/json");
}

function exportUserJs() {
  const text = `"use strict";\n\nwindow.PARKING_LAYOUT_SCHEMA_VERSION = 1;\nwindow.PARKING_LAYOUTS = Object.freeze(${JSON.stringify(state.layouts, null, 2)});\n`;
  downloadText("parking-layouts.js", text, "text/javascript");
}

async function importJson(file) {
  if (!file) {
    return;
  }
  const data = JSON.parse(await file.text());
  if (!data || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("レイアウトJSONの形式が正しくありません。");
  }
  Object.values(data).forEach((layout) => {
    if (!layout || typeof layout !== "object" || !layout.facilityId || !Array.isArray(layout.objects)) {
      throw new Error("facilityId または objects が不足しています。");
    }
  });
  state.layouts = data;
  ensureLayout(state.facilityId);
  state.selectedUid = null;
  saveLocal();
  render();
}

/* =========================================================
   テーマと初期化
   ========================================================= */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  elements.themeButton.textContent = theme === "dark" ? "ライトモード" : "ダークモード";
  try {
    localStorage.setItem("parkingAdminTheme", theme);
  } catch {}
}

function initializeTheme() {
  let theme = null;
  try {
    theme = localStorage.getItem("parkingAdminTheme");
  } catch {}
  if (theme !== "dark" && theme !== "light") {
    theme = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  applyTheme(theme);
}

function getExperimentFacility() {
  return {
    id: "ous-main-gate-experiment",
    name: "実験用駐車場（岡山理科大学正門）",
    prefecture: "岡山県",
  };
}

function renderFacilityOptions(prefecture, preferredFacilityId = null) {
  const experiment = getExperimentFacility();
  const facilities = state.facilities.filter((facility) => facility.prefecture === prefecture);

  elements.facilitySelect.replaceChildren();

  if (prefecture === experiment.prefecture) {
    elements.facilitySelect.add(
      new Option(`${experiment.name}`, experiment.id),
    );
  }

  facilities.forEach((facility) => {
    elements.facilitySelect.add(new Option(facility.name, facility.id));
  });

  if (preferredFacilityId
      && [...elements.facilitySelect.options].some((option) => option.value === preferredFacilityId)) {
    elements.facilitySelect.value = preferredFacilityId;
  }

  state.facilityId = elements.facilitySelect.value || null;

  if (state.facilityId) {
    ensureLayout(state.facilityId);
    elements.facilityId.textContent = `facilityId: ${state.facilityId}`;
  } else {
    elements.facilityId.textContent = "該当する施設がありません。";
  }
}

function initializeFacilities() {
  const prefectures = [...new Set(state.facilities.map((facility) => facility.prefecture))];
  const experiment = getExperimentFacility();

  if (!prefectures.includes(experiment.prefecture)) {
    prefectures.push(experiment.prefecture);
  }

  elements.prefectureSelect.replaceChildren();
  prefectures.forEach((prefecture) => {
    elements.prefectureSelect.add(new Option(prefecture, prefecture));
  });

  const initialPrefecture = prefectures.includes("岡山県") ? "岡山県" : prefectures[0];
  elements.prefectureSelect.value = initialPrefecture;
  renderFacilityOptions(initialPrefecture);
}

function changePrefecture() {
  state.selectedUid = null;
  renderFacilityOptions(elements.prefectureSelect.value);
  render();
}

function changeFacility() {
  state.facilityId = elements.facilitySelect.value;
  state.selectedUid = null;
  ensureLayout(state.facilityId);
  elements.facilityId.textContent = `facilityId: ${state.facilityId}`;
  render();
}

function updateCanvasSettings() {
  const layout = getCurrentLayout();
  if (!layout) {
    return;
  }
  layout.canvas.width = Math.max(400, Number(elements.canvasWidth.value) || 1000);
  layout.canvas.height = Math.max(300, Number(elements.canvasHeight.value) || 700);
  const scale = Number(elements.canvasScale.value);
  layout.canvas.scaleMetersPerPixel = Number.isFinite(scale) && scale > 0 ? scale : null;
  saveLocal();
  render();
}

/* =========================================================
   イベント
   ========================================================= */

document.querySelectorAll("[data-add-object]").forEach((button) => {
  button.addEventListener("click", () => addObject(button.dataset.addObject, {
    spaceType: button.dataset.spaceType,
    trafficDirection: button.dataset.trafficDirection,
    accessType: button.dataset.accessType,
  }));
});

elements.canvas.addEventListener("click", () => {
  state.selectedUid = null;
  render();
});
elements.canvas.addEventListener("pointermove", moveDrag);
elements.canvas.addEventListener("pointerup", endDrag);
elements.canvas.addEventListener("pointercancel", endDrag);

elements.prefectureSelect.addEventListener("change", changePrefecture);
elements.facilitySelect.addEventListener("change", changeFacility);
[elements.name, elements.x, elements.y, elements.rotation, elements.width, elements.height,
  elements.roadDirection, elements.parkingAccessType,
  elements.spaceType, elements.spaceStatus, elements.entranceType, elements.publicAccess,
  elements.wheelchairAccessible, elements.guideTarget, elements.buildingId].forEach((control) => {
  control.addEventListener("change", updateSelectedFromForm);
});

document.querySelector("#duplicate-button").addEventListener("click", duplicateSelected);
document.querySelector("#delete-button").addEventListener("click", deleteSelected);
document.querySelector("#save-button").addEventListener("click", saveLocal);
document.querySelector("#export-json-button").addEventListener("click", exportJson);
document.querySelector("#export-js-button").addEventListener("click", exportUserJs);
document.querySelector("#import-file").addEventListener("change", async (event) => {
  try {
    await importJson(event.target.files[0]);
  } catch (error) {
    alert(error.message);
  } finally {
    event.target.value = "";
  }
});
[elements.canvasWidth, elements.canvasHeight, elements.canvasScale].forEach((control) => control.addEventListener("change", updateCanvasSettings));
elements.themeButton.addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

document.addEventListener("keydown", (event) => {
  if ((event.key === "Delete" || event.key === "Backspace") && !event.target.matches("input, select, textarea")) {
    deleteSelected();
  }
});

restoreLocal();
initializeTheme();
initializeFacilities();
render();
