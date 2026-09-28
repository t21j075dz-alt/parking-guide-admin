"use strict";

/* =========================================================
   【このファイルの役割】
   管理者が駐車場レイアウトを作成・編集するための画面制御を担当する。

   主な責務：
   1. facilityId 単位でレイアウトを作成・切替
   2. 駐車区画・道路・建物・各種設備の追加／移動／編集
   3. 国土地理院の航空写真を編集用の下敷きとして描画
   4. localStorage への端末内保存
   5. Supabase設定時は編集内容をクラウドへ自動反映
   6. JSON・parking-layouts.js の入出力によるバックアップ

   座標 x / y は画面表示用CSS座標ではなく、各施設のキャンバス上の
   論理座標として保存する。ユーザーアプリはこの座標を百分率へ変換して表示する。
   ========================================================= */

/* =========================================================
   駐車場マップ管理：状態と定義
   ========================================================= */

/* 建物出入口の内部値と画面表示の対応。保存値は英字で固定し、表示文言と分離する。 */
const ENTRANCE_LABELS = {
  main: "正面入口",
  sub: "その他の一般入口",
  accessible: "バリアフリー入口",
  staff: "従業員入口",
  other: "その他",
};

/* オブジェクト追加時の初期寸法と名称。寸法はキャンバス上の論理ピクセル。 */
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

/* 画面全体で共有する編集状態。layouts は facilityId をキーにしたレイアウト辞書。 */
const state = {
  facilities: window.ADMIN_FACILITY_CATALOG?.facilities ?? [],
  layouts: {},
  facilityId: null,
  selectedUid: null,
  drag: null,
  resize: null,
  backgroundEdit: false,
  backgroundDrag: null,
  remoteAccessToken: null,
  remoteSyncTimer: null,
};

/* 頻繁に参照するDOM要素を初期化時にまとめて保持する。 */
const elements = {
  prefectureSelect: document.querySelector("#prefecture-select"),
  facilitySelect: document.querySelector("#facility-select"),
  facilityId: document.querySelector("#facility-id"),
  canvas: document.querySelector("#map-canvas"),
  canvasWidth: document.querySelector("#canvas-width"),
  canvasHeight: document.querySelector("#canvas-height"),
  canvasScale: document.querySelector("#canvas-scale"),
  backgroundType: document.querySelector("#background-type"),
  backgroundLatitude: document.querySelector("#background-latitude"),
  backgroundLongitude: document.querySelector("#background-longitude"),
  backgroundZoom: document.querySelector("#background-zoom"),
  backgroundOpacity: document.querySelector("#background-opacity"),
  backgroundStatus: document.querySelector("#background-status"),
  backgroundEditButton: document.querySelector("#background-edit-button"),
  snapEnabled: document.querySelector("#snap-enabled"),
  adjacentCount: document.querySelector("#adjacent-count"),
  cloudStatus: document.querySelector("#cloud-sync-status"),
  cloudEmail: document.querySelector("#cloud-email"),
  cloudPassword: document.querySelector("#cloud-password"),
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

/** facilityId に対応する編集用レイアウトを取得し、未作成なら初期状態を生成する。 */
function ensureLayout(facilityId) {
  if (!state.layouts[facilityId]) {
    state.layouts[facilityId] = {
      schemaVersion: 1,
      facilityId,
      canvas: { width: 1000, height: 700, scaleMetersPerPixel: null },
      background: null,
      objects: [],
    };
  }
  return state.layouts[facilityId];
}

/** キャンバス上で現在選択されているオブジェクトを取得する。 */
function getSelectedObject() {
  return getCurrentLayout()?.objects.find((item) => item.uid === state.selectedUid) ?? null;
}

/** オブジェクト種別ごとに重複しない内部IDを生成する。 */
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

/** 左側ツールから指定された種類のオブジェクトをキャンバス中央へ追加する。 */
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
   航空写真の背景
   ========================================================= */

/** Web Mercator の緯度上限内へ収める。 */
function clampLatitude(latitude) {
  return Math.max(-85.05112878, Math.min(85.05112878, latitude));
}

/** 緯度経度を指定ズームの世界ピクセル座標へ変換する。 */
function toWorldPixel(latitude, longitude, zoom) {
  const size = 256 * (2 ** zoom);
  const lat = clampLatitude(latitude) * Math.PI / 180;
  return {
    x: ((longitude + 180) / 360) * size,
    y: (1 - Math.log(Math.tan(lat) + (1 / Math.cos(lat))) / Math.PI) / 2 * size,
  };
}

/** 世界ピクセル座標を緯度経度へ戻す。航空写真をドラッグした後の中心座標更新に使用する。 */
function fromWorldPixel(x, y, zoom) {
  const size = 256 * (2 ** zoom);
  const longitude = x / size * 360 - 180;
  const n = Math.PI - 2 * Math.PI * y / size;
  const latitude = 180 / Math.PI * Math.atan(Math.sinh(n));
  return { latitude, longitude };
}

/** 現在の背景設定を入力欄へ反映する。 */
function updateBackgroundControls(layout) {
  const background = layout.background;
  elements.backgroundType.value = background?.type ?? "none";
  elements.backgroundLatitude.value = Number.isFinite(background?.centerLat) ? background.centerLat : "";
  elements.backgroundLongitude.value = Number.isFinite(background?.centerLng) ? background.centerLng : "";
  elements.backgroundZoom.value = Number.isFinite(background?.zoom) ? background.zoom : 18;
  elements.backgroundOpacity.value = Number.isFinite(background?.opacity) ? background.opacity : 0.75;
}

/** 国土地理院の航空写真タイルをキャンバス背景として描画する。 */
function renderBackground(layout) {
  const background = layout.background;
  if (!background || background.type !== "gsi-seamlessphoto") {
    return;
  }
  if (!Number.isFinite(background.centerLat) || !Number.isFinite(background.centerLng)) {
    return;
  }

  const zoom = Math.max(14, Math.min(18, Math.round(background.zoom ?? 18)));
  const tileCount = 2 ** zoom;
  const center = toWorldPixel(background.centerLat, background.centerLng, zoom);
  const topLeftX = center.x - layout.canvas.width / 2;
  const topLeftY = center.y - layout.canvas.height / 2;
  const startTileX = Math.floor(topLeftX / 256);
  const endTileX = Math.floor((topLeftX + layout.canvas.width) / 256);
  const startTileY = Math.floor(topLeftY / 256);
  const endTileY = Math.floor((topLeftY + layout.canvas.height) / 256);

  const layer = document.createElement("div");
  layer.className = "satellite-layer";
  layer.style.opacity = String(background.opacity ?? 0.75);

  for (let tileY = startTileY; tileY <= endTileY; tileY += 1) {
    if (tileY < 0 || tileY >= tileCount) {
      continue;
    }
    for (let tileX = startTileX; tileX <= endTileX; tileX += 1) {
      const wrappedX = ((tileX % tileCount) + tileCount) % tileCount;
      const image = document.createElement("img");
      image.alt = "";
      image.draggable = false;
      image.src = `https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/${zoom}/${wrappedX}/${tileY}.jpg`;
      image.style.left = `${tileX * 256 - topLeftX}px`;
      image.style.top = `${tileY * 256 - topLeftY}px`;
      layer.append(image);
    }
  }

  elements.canvas.append(layer);
}

/** 航空写真が未設定の場合、施設座標または入力済み座標を使って初期表示する。 */
function enableBackground() {
  const layout = getCurrentLayout();
  if (!layout) {
    return;
  }
  if (!layout.background) {
    const experiment = getExperimentFacility();
    const facility = state.facilityId === experiment.id
      ? experiment
      : state.facilities.find((item) => item.id === state.facilityId);
    const inputLat = Number(elements.backgroundLatitude.value);
    const inputLng = Number(elements.backgroundLongitude.value);
    const centerLat = Number.isFinite(facility?.latitude) ? facility.latitude : inputLat;
    const centerLng = Number.isFinite(facility?.longitude) ? facility.longitude : inputLng;
    if (!Number.isFinite(centerLat) || !Number.isFinite(centerLng)) {
      elements.backgroundStatus.textContent = "この施設には座標がありません。現在地を使うか、詳細設定で緯度・経度を入力してください。";
      return;
    }
    layout.background = {
      type: "gsi-seamlessphoto",
      centerLat,
      centerLng,
      zoom: 18,
      opacity: Number(elements.backgroundOpacity.value) || 0.75,
    };
  } else {
    layout.background.type = "gsi-seamlessphoto";
  }
  saveLocal();
  render();
  elements.backgroundStatus.textContent = "航空写真を表示しました。「写真を動かす」で位置合わせできます。";
}

/** 写真調整モードを切り替える。調整中はオブジェクトより背景操作を優先する。 */
function toggleBackgroundEdit() {
  const layout = getCurrentLayout();
  if (!layout?.background) {
    enableBackground();
  }
  if (!getCurrentLayout()?.background) {
    return;
  }
  state.backgroundEdit = !state.backgroundEdit;
  elements.backgroundEditButton.setAttribute("aria-pressed", String(state.backgroundEdit));
  elements.backgroundEditButton.textContent = state.backgroundEdit ? "写真調整を終了" : "写真を動かす";
  elements.canvas.classList.toggle("is-background-editing", state.backgroundEdit);
  elements.backgroundStatus.textContent = state.backgroundEdit
    ? "写真調整中：航空写真をドラッグ、ホイールまたは＋/－で拡大縮小できます。"
    : "オブジェクト編集に戻りました。";
}

/** 航空写真のズーム値を1段階変更する。 */
function changeBackgroundZoom(delta) {
  const layout = getCurrentLayout();
  if (!layout?.background) {
    enableBackground();
  }
  if (!layout?.background) {
    return;
  }
  layout.background.zoom = Math.max(14, Math.min(18, Math.round((layout.background.zoom ?? 18) + delta)));
  saveLocal();
  render();
}

/** 写真調整モードで背景のドラッグを開始する。 */
function startBackgroundDrag(event) {
  const layout = getCurrentLayout();
  if (!state.backgroundEdit || !layout?.background || event.button !== 0) {
    return false;
  }
  const zoom = layout.background.zoom ?? 18;
  state.backgroundDrag = {
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    centerWorld: toWorldPixel(layout.background.centerLat, layout.background.centerLng, zoom),
    zoom,
  };
  elements.canvas.setPointerCapture(event.pointerId);
  elements.canvas.classList.add("is-panning");
  event.preventDefault();
  return true;
}

/** 背景ドラッグ中は画像レイヤーだけを追従させ、軽い操作感を保つ。 */
function moveBackgroundDrag(event) {
  if (!state.backgroundDrag || event.pointerId !== state.backgroundDrag.pointerId) {
    return;
  }
  const dx = event.clientX - state.backgroundDrag.startClientX;
  const dy = event.clientY - state.backgroundDrag.startClientY;
  const layer = elements.canvas.querySelector(".satellite-layer");
  if (layer) {
    layer.style.transform = `translate(${dx}px, ${dy}px)`;
  }
}

/** 背景ドラッグ終了時に移動量を緯度経度へ変換して保存する。 */
function endBackgroundDrag(event) {
  if (!state.backgroundDrag || event.pointerId !== state.backgroundDrag.pointerId) {
    return false;
  }
  const layout = getCurrentLayout();
  const dx = event.clientX - state.backgroundDrag.startClientX;
  const dy = event.clientY - state.backgroundDrag.startClientY;
  const center = state.backgroundDrag.centerWorld;
  const next = fromWorldPixel(center.x - dx, center.y - dy, state.backgroundDrag.zoom);
  layout.background.centerLat = next.latitude;
  layout.background.centerLng = next.longitude;
  state.backgroundDrag = null;
  elements.canvas.classList.remove("is-panning");
  saveLocal();
  render();
  return true;
}

/** 背景設定を保存して再描画する。 */
function applyBackgroundSettings() {
  const layout = getCurrentLayout();
  if (!layout) {
    return;
  }

  if (elements.backgroundType.value === "none") {
    layout.background = null;
    saveLocal();
    render();
    return;
  }

  const centerLat = Number(elements.backgroundLatitude.value);
  const centerLng = Number(elements.backgroundLongitude.value);
  const zoom = Number(elements.backgroundZoom.value);
  const opacity = Number(elements.backgroundOpacity.value);

  if (!Number.isFinite(centerLat) || !Number.isFinite(centerLng)
      || Math.abs(centerLat) > 90 || Math.abs(centerLng) > 180) {
    elements.backgroundStatus.textContent = "緯度・経度を入力してください。";
    return;
  }

  layout.background = {
    type: "gsi-seamlessphoto",
    centerLat,
    centerLng,
    zoom: Math.max(14, Math.min(18, Math.round(zoom || 18))),
    opacity: Math.max(0.15, Math.min(1, opacity || 0.75)),
  };
  elements.backgroundStatus.textContent = "航空写真を更新しました。背景を合わせてからオブジェクトを配置してください。";
  saveLocal();
  render();
}

/** ブラウザーの現在地を航空写真の中心に設定する。 */
function useCurrentLocationForBackground() {
  if (!navigator.geolocation) {
    elements.backgroundStatus.textContent = "このブラウザーでは現在地を取得できません。";
    return;
  }
  elements.backgroundStatus.textContent = "現在地を取得しています…";
  navigator.geolocation.getCurrentPosition(
    (position) => {
      elements.backgroundType.value = "gsi-seamlessphoto";
      elements.backgroundLatitude.value = position.coords.latitude.toFixed(6);
      elements.backgroundLongitude.value = position.coords.longitude.toFixed(6);
      elements.backgroundZoom.value = 18;
      applyBackgroundSettings();
    },
    () => {
      elements.backgroundStatus.textContent = "現在地を取得できませんでした。緯度・経度を直接入力してください。";
    },
    { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
  );
}


/* =========================================================
   オブジェクトの直接操作・吸着・連続生成
   ========================================================= */

/** 指定値を5pxグリッドへ丸める。吸着OFFの場合は元の値を返す。 */
function snapToGrid(value) {
  return elements.snapEnabled?.checked ? Math.round(value / 5) * 5 : value;
}

/** 移動中の枠を近くの枠の端・中心へ吸着させる。 */
function snapObjectPosition(item, x, y) {
  if (!elements.snapEnabled?.checked) {
    return { x, y, guideX: null, guideY: null };
  }
  const threshold = 8;
  const layout = getCurrentLayout();
  const width = item.width ?? 34;
  const height = item.height ?? 34;
  let bestX = { value: snapToGrid(x), distance: Math.abs(snapToGrid(x) - x), guide: null };
  let bestY = { value: snapToGrid(y), distance: Math.abs(snapToGrid(y) - y), guide: null };

  layout.objects.forEach((other) => {
    if (other.uid === item.uid) {
      return;
    }
    const ow = other.width ?? 34;
    const oh = other.height ?? 34;
    const xCandidates = [
      [other.x, other.x],
      [other.x + ow, other.x + ow],
      [other.x - width, other.x],
      [other.x + ow - width, other.x + ow],
      [other.x + ow / 2 - width / 2, other.x + ow / 2],
    ];
    const yCandidates = [
      [other.y, other.y],
      [other.y + oh, other.y + oh],
      [other.y - height, other.y],
      [other.y + oh - height, other.y + oh],
      [other.y + oh / 2 - height / 2, other.y + oh / 2],
    ];
    xCandidates.forEach(([candidate, guide]) => {
      const distance = Math.abs(candidate - x);
      if (distance <= threshold && distance < bestX.distance) {
        bestX = { value: candidate, distance, guide };
      }
    });
    yCandidates.forEach(([candidate, guide]) => {
      const distance = Math.abs(candidate - y);
      if (distance <= threshold && distance < bestY.distance) {
        bestY = { value: candidate, distance, guide };
      }
    });
  });

  return { x: bestX.value, y: bestY.value, guideX: bestX.guide, guideY: bestY.guide };
}

/** 吸着位置を示す補助線をキャンバス上へ表示する。 */
function showSnapGuides(guideX, guideY) {
  elements.canvas.querySelectorAll(".snap-guide").forEach((node) => node.remove());
  if (Number.isFinite(guideX)) {
    const line = document.createElement("div");
    line.className = "snap-guide snap-guide--vertical";
    line.style.left = `${guideX}px`;
    elements.canvas.append(line);
  }
  if (Number.isFinite(guideY)) {
    const line = document.createElement("div");
    line.className = "snap-guide snap-guide--horizontal";
    line.style.top = `${guideY}px`;
    elements.canvas.append(line);
  }
}

/** 選択枠の周囲にPowerPoint風の8個のリサイズハンドルを付ける。 */
function addResizeHandles(node, item) {
  if (["buildingEntrance", "parkingEntrance", "noEntry", "evCharger"].includes(item.objectType)) {
    return;
  }
  ["nw", "n", "ne", "e", "se", "s", "sw", "w"].forEach((direction) => {
    const handle = document.createElement("button");
    handle.type = "button";
    handle.className = `resize-handle resize-handle--${direction}`;
    handle.dataset.resizeDirection = direction;
    handle.setAttribute("aria-label", "サイズ変更");
    handle.addEventListener("pointerdown", startResize);
    node.append(handle);
  });
}

/** リサイズハンドルのドラッグを開始する。 */
function startResize(event) {
  event.stopPropagation();
  event.preventDefault();
  const node = event.currentTarget.closest(".map-object");
  const item = getCurrentLayout()?.objects.find((object) => object.uid === node?.dataset.uid);
  if (!item) {
    return;
  }
  state.selectedUid = item.uid;
  state.resize = {
    pointerId: event.pointerId,
    direction: event.currentTarget.dataset.resizeDirection,
    startClientX: event.clientX,
    startClientY: event.clientY,
    x: item.x,
    y: item.y,
    width: item.width ?? 34,
    height: item.height ?? 34,
    rotation: Number(item.rotation) || 0,
  };
  event.currentTarget.setPointerCapture(event.pointerId);
}

/** ハンドル移動量を選択枠のローカル方向へ変換して幅・高さを更新する。 */
function moveResize(event) {
  if (!state.resize || event.pointerId !== state.resize.pointerId) {
    return;
  }
  const item = getSelectedObject();
  const layout = getCurrentLayout();
  if (!item || !layout) {
    return;
  }
  const dx = event.clientX - state.resize.startClientX;
  const dy = event.clientY - state.resize.startClientY;
  const radians = state.resize.rotation * Math.PI / 180;
  const localDx = dx * Math.cos(radians) + dy * Math.sin(radians);
  const localDy = -dx * Math.sin(radians) + dy * Math.cos(radians);
  const direction = state.resize.direction;
  const sx = direction.includes("e") ? 1 : direction.includes("w") ? -1 : 0;
  const sy = direction.includes("s") ? 1 : direction.includes("n") ? -1 : 0;
  const minSize = 12;
  const requestedWidth = sx === 0 ? state.resize.width : state.resize.width + sx * localDx;
  const requestedHeight = sy === 0 ? state.resize.height : state.resize.height + sy * localDy;
  const newWidth = Math.max(minSize, snapToGrid(requestedWidth));
  const newHeight = Math.max(minSize, snapToGrid(requestedHeight));

  const actualLocalShiftX = sx === 0 ? 0 : sx * (newWidth - state.resize.width) / 2;
  const actualLocalShiftY = sy === 0 ? 0 : sy * (newHeight - state.resize.height) / 2;
  const globalShiftX = actualLocalShiftX * Math.cos(radians) - actualLocalShiftY * Math.sin(radians);
  const globalShiftY = actualLocalShiftX * Math.sin(radians) + actualLocalShiftY * Math.cos(radians);
  const oldCenterX = state.resize.x + state.resize.width / 2;
  const oldCenterY = state.resize.y + state.resize.height / 2;

  item.width = newWidth;
  item.height = newHeight;
  item.x = Math.max(0, Math.min(layout.canvas.width - newWidth, oldCenterX + globalShiftX - newWidth / 2));
  item.y = Math.max(0, Math.min(layout.canvas.height - newHeight, oldCenterY + globalShiftY - newHeight / 2));

  const node = elements.canvas.querySelector(`[data-uid="${CSS.escape(item.uid)}"]`);
  if (node) {
    node.style.left = `${item.x}px`;
    node.style.top = `${item.y}px`;
    node.style.width = `${item.width}px`;
    node.style.height = `${item.height}px`;
  }
  elements.x.value = Math.round(item.x);
  elements.y.value = Math.round(item.y);
  elements.width.value = Math.round(item.width);
  elements.height.value = Math.round(item.height);
}

/** リサイズ終了時に変更結果を保存する。 */
function endResize(event) {
  if (!state.resize || event.pointerId !== state.resize.pointerId) {
    return false;
  }
  state.resize = null;
  saveLocal();
  render();
  return true;
}

/** 選択中の駐車枠と同じ枠を指定方向へ隙間なく連続生成する。 */
function createAdjacentSpaces(direction) {
  const source = getSelectedObject();
  const layout = getCurrentLayout();
  if (!source || source.objectType !== "parkingSpace" || !layout) {
    return;
  }
  const count = Math.max(1, Math.min(50, Number(elements.adjacentCount?.value) || 1));
  const radians = (Number(source.rotation) || 0) * Math.PI / 180;
  const local = {
    right: [source.width, 0],
    left: [-source.width, 0],
    down: [0, source.height],
    up: [0, -source.height],
  }[direction];
  if (!local) {
    return;
  }
  const stepX = local[0] * Math.cos(radians) - local[1] * Math.sin(radians);
  const stepY = local[0] * Math.sin(radians) + local[1] * Math.cos(radians);
  let lastUid = source.uid;

  for (let index = 1; index <= count; index += 1) {
    const copy = structuredClone(source);
    copy.uid = createUid("parkingSpace");
    const label = copy.spaceType === "compact" ? "軽"
      : copy.spaceType === "accessible" ? "車椅子"
        : copy.spaceType === "ev" ? "EV" : "普通車";
    copy.name = `${label} ${copy.uid.replace("space_", "")}`;
    copy.x = Math.round(source.x + stepX * index);
    copy.y = Math.round(source.y + stepY * index);
    if (copy.x < 0 || copy.y < 0
        || copy.x + copy.width > layout.canvas.width
        || copy.y + copy.height > layout.canvas.height) {
      break;
    }
    layout.objects.push(copy);
    lastUid = copy.uid;
  }

  state.selectedUid = lastUid;
  saveLocal();
  render();
}

/** 選択オブジェクトを90度単位で回転する。 */
function rotateSelected(delta) {
  const item = getSelectedObject();
  if (!item) {
    return;
  }
  item.rotation = ((Number(item.rotation) || 0) + delta + 360) % 360;
  saveLocal();
  render();
}

/* =========================================================
   描画・選択・ドラッグ
   ========================================================= */

/** 背景と全オブジェクトを現在の編集状態から描画する。 */
function render() {
  const layout = ensureLayout(state.facilityId);
  elements.canvas.style.width = `${layout.canvas.width}px`;
  elements.canvas.style.height = `${layout.canvas.height}px`;
  elements.canvasWidth.value = layout.canvas.width;
  elements.canvasHeight.value = layout.canvas.height;
  elements.canvasScale.value = layout.canvas.scaleMetersPerPixel ?? "";
  updateBackgroundControls(layout);
  elements.canvas.replaceChildren();
  renderBackground(layout);

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
    if (item.uid === state.selectedUid) {
      addResizeHandles(node, item);
    }
    node.addEventListener("pointerdown", startDrag);
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      selectObject(item.uid);
    });
    elements.canvas.append(node);
  });
  updateSettings();
}

/** 指定UIDのオブジェクトを選択状態にする。 */
function selectObject(uid) {
  state.selectedUid = uid;
  render();
}

/** ポインター操作開始時の座標を記録し、ドラッグ移動を開始する。 */
function startDrag(event) {
  if (state.backgroundEdit || event.target.closest(".resize-handle") || event.button !== 0) {
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

/** ドラッグ中のポインター移動量からオブジェクト座標を更新する。 */
function moveDrag(event) {
  if (!state.drag || event.pointerId !== state.drag.pointerId) {
    return;
  }
  const item = getSelectedObject();
  const layout = getCurrentLayout();
  if (!item || !layout) {
    return;
  }
  const proposedX = Math.max(0, Math.min(
    layout.canvas.width - (item.width ?? 34),
    state.drag.startX + event.clientX - state.drag.startClientX,
  ));
  const proposedY = Math.max(0, Math.min(
    layout.canvas.height - (item.height ?? 34),
    state.drag.startY + event.clientY - state.drag.startClientY,
  ));
  const snapped = snapObjectPosition(item, proposedX, proposedY);
  item.x = Math.round(snapped.x);
  item.y = Math.round(snapped.y);
  showSnapGuides(snapped.guideX, snapped.guideY);
  const node = elements.canvas.querySelector(`[data-uid="${CSS.escape(item.uid)}"]`);
  if (node) {
    node.style.left = `${item.x}px`;
    node.style.top = `${item.y}px`;
  }
  elements.x.value = item.x;
  elements.y.value = item.y;
}

/** ドラッグ操作を終了し、更新後の位置を端末内とクラウド同期対象へ保存する。 */
function endDrag(event) {
  if (!state.drag || event.pointerId !== state.drag.pointerId) {
    return;
  }
  state.drag = null;
  elements.canvas.querySelectorAll(".snap-guide").forEach((node) => node.remove());
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

/** 右側設定フォームの変更内容を選択オブジェクトへ反映する。 */
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
    const previousDirection = item.trafficDirection ?? "twoWay";
    const previousDefaultName = previousDirection === "oneWay" ? "一方通行" : "車道";
    item.trafficDirection = elements.roadDirection.value;
    if (item.name === previousDefaultName) {
      item.name = item.trafficDirection === "oneWay" ? "一方通行" : "車道";
      elements.name.value = item.name;
    }
  }
  if (item.objectType === "parkingEntrance") {
    const accessNames = {
      entrance: "駐車場入口",
      exit: "駐車場出口",
      both: "駐車場出入口",
    };
    const previousAccessType = item.accessType ?? "both";
    item.accessType = elements.parkingAccessType.value;
    if (item.name === accessNames[previousAccessType]) {
      item.name = accessNames[item.accessType];
      elements.name.value = item.name;
    }
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

/** 選択オブジェクトを新しいUIDで複製し、少しずらした位置へ配置する。 */
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

/** 選択オブジェクトを現在施設のレイアウトから削除する。 */
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
   Supabaseを使った自動反映
   ========================================================= */

/** 公開設定が入力済みか確認する。秘密鍵は使用しない。 */
function getRemoteConfig() {
  const config = window.PARKING_REMOTE_CONFIG ?? {};
  const url = String(config.supabaseUrl ?? "").replace(/\/$/, "");
  const publishableKey = String(config.publishableKey ?? "");
  return {
    enabled: config.enabled === true && /^https:\/\//.test(url) && publishableKey.length > 10,
    url,
    publishableKey,
  };
}

/** クラウド同期状態の表示を更新する。 */
function updateCloudStatus(message = null) {
  const config = getRemoteConfig();
  if (message) {
    elements.cloudStatus.textContent = message;
    return;
  }
  if (!config.enabled) {
    elements.cloudStatus.textContent = "クラウド連携は未設定です。sync-config.js を設定してください。";
  } else if (state.remoteAccessToken) {
    elements.cloudStatus.textContent = "ログイン済みです。編集内容は自動反映されます。";
  } else {
    elements.cloudStatus.textContent = "クラウド連携設定済みです。管理者ログインが必要です。";
  }
}

/** Supabase Authにメール・パスワードでログインする。 */
async function remoteLogin() {
  const config = getRemoteConfig();
  if (!config.enabled) {
    updateCloudStatus("sync-config.js の Supabase 設定が必要です。");
    return;
  }
  const email = elements.cloudEmail.value.trim();
  const password = elements.cloudPassword.value;
  if (!email || !password) {
    updateCloudStatus("管理者メールとパスワードを入力してください。");
    return;
  }

  updateCloudStatus("ログインしています…");
  const response = await fetch(`${config.url}/auth/v1/token?grant_type=password`, {
    method: "POST",
    headers: {
      apikey: config.publishableKey,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.access_token) {
    updateCloudStatus("ログインできませんでした。メール・パスワードとSupabase設定を確認してください。");
    return;
  }

  state.remoteAccessToken = data.access_token;
  sessionStorage.setItem("parkingAdminRemoteToken", state.remoteAccessToken);
  elements.cloudPassword.value = "";
  updateCloudStatus("ログインしました。以後の編集は自動反映されます。");
}

/** 現在施設のレイアウトをクラウドへ保存する。 */
async function syncCurrentLayout() {
  const config = getRemoteConfig();
  const layout = getCurrentLayout();
  if (!config.enabled || !state.remoteAccessToken || !layout) {
    return false;
  }

  const response = await fetch(`${config.url}/rest/v1/parking_layouts?on_conflict=facility_id`, {
    method: "POST",
    headers: {
      apikey: config.publishableKey,
      Authorization: `Bearer ${state.remoteAccessToken}`,
      "Content-Type": "application/json",
      Prefer: "resolution=merge-duplicates,return=minimal",
    },
    body: JSON.stringify({
      facility_id: layout.facilityId,
      layout_data: layout,
      updated_at: new Date().toISOString(),
    }),
  });

  if (response.ok) {
    updateCloudStatus(`自動反映済み：${new Date().toLocaleTimeString("ja-JP")}`);
    return true;
  }

  if (response.status === 401) {
    state.remoteAccessToken = null;
    sessionStorage.removeItem("parkingAdminRemoteToken");
    updateCloudStatus("ログインの有効期限が切れました。もう一度ログインしてください。");
  } else {
    updateCloudStatus("クラウド保存に失敗しました。SupabaseのRLS設定を確認してください。");
  }
  return false;
}

/** 連続編集時の通信をまとめ、約1秒後に現在施設を保存する。 */
function scheduleRemoteSync() {
  if (!getRemoteConfig().enabled || !state.remoteAccessToken) {
    return;
  }
  if (state.remoteSyncTimer !== null) {
    clearTimeout(state.remoteSyncTimer);
  }
  state.remoteSyncTimer = setTimeout(() => {
    state.remoteSyncTimer = null;
    void syncCurrentLayout();
  }, 1000);
}

/** クラウド上の全レイアウトを取得して端末内データへ反映する。 */
async function loadRemoteLayouts() {
  const config = getRemoteConfig();
  if (!config.enabled || !state.remoteAccessToken) {
    updateCloudStatus("クラウドから読むには管理者ログインが必要です。");
    return;
  }
  updateCloudStatus("クラウドから読み込んでいます…");
  const response = await fetch(`${config.url}/rest/v1/parking_layouts?select=facility_id,layout_data`, {
    headers: {
      apikey: config.publishableKey,
      Authorization: `Bearer ${state.remoteAccessToken}`,
    },
  });
  if (!response.ok) {
    updateCloudStatus("クラウドから読み込めませんでした。");
    return;
  }
  const rows = await response.json();
  rows.forEach((row) => {
    if (row?.facility_id && row.layout_data && Array.isArray(row.layout_data.objects)) {
      state.layouts[row.facility_id] = row.layout_data;
    }
  });
  localStorage.setItem("parkingAdminLayoutsV1", JSON.stringify(state.layouts));
  ensureLayout(state.facilityId);
  render();
  updateCloudStatus(`クラウドから${rows.length}件読み込みました。`);
}

/** 保存済みセッションがあれば自動反映を再開する。 */
function restoreRemoteSession() {
  if (!getRemoteConfig().enabled) {
    updateCloudStatus();
    return;
  }
  state.remoteAccessToken = sessionStorage.getItem("parkingAdminRemoteToken");
  updateCloudStatus();
}

/** 管理者ログアウト。端末内レイアウトは消さない。 */
function remoteLogout() {
  state.remoteAccessToken = null;
  sessionStorage.removeItem("parkingAdminRemoteToken");
  updateCloudStatus("クラウドからログアウトしました。端末内の編集データは残っています。");
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
  scheduleRemoteSync();
}

/** localStorageに保存された編集データを起動時に復元する。 */
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

/** 文字列をBlob化し、指定ファイル名でブラウザーへダウンロードさせる。 */
function downloadText(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** 全レイアウトをバックアップ・再読込用JSONとして出力する。 */
function exportJson() {
  downloadText("parking-layouts.json", `${JSON.stringify(state.layouts, null, 2)}\n`, "application/json");
}

/** クラウド未使用時の互換手段としてユーザー用 parking-layouts.js を出力する。 */
function exportUserJs() {
  const text = `"use strict";\n\nwindow.PARKING_LAYOUT_SCHEMA_VERSION = 1;\nwindow.PARKING_LAYOUTS = Object.freeze(${JSON.stringify(state.layouts, null, 2)});\n`;
  downloadText("parking-layouts.js", text, "text/javascript");
}

/** 管理画面から選択したレイアウトJSONを検証して読み込む。 */
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

/** 保存済みテーマを復元し、未設定ならOSの配色設定を初期値にする。 */
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

/** 岡山理科大学正門の実験用駐車場情報を管理画面向けに返す。 */
function getExperimentFacility() {
  return {
    id: "ous-main-gate-experiment",
    name: "実験用駐車場（岡山理科大学正門）",
    prefecture: "岡山県",
    latitude: 34.6998,
    longitude: 133.9280,
  };
}

/** 選択した都道府県に属する施設だけを施設プルダウンへ表示する。 */
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
    const layout = ensureLayout(state.facilityId);
    const facility = state.facilityId === experiment.id
      ? experiment
      : state.facilities.find((item) => item.id === state.facilityId);
    if (!layout.background && Number.isFinite(facility?.latitude) && Number.isFinite(facility?.longitude)) {
      layout.background = {
        type: "gsi-seamlessphoto",
        centerLat: facility.latitude,
        centerLng: facility.longitude,
        zoom: 18,
        opacity: 0.75,
      };
    }
    elements.facilityId.textContent = `facilityId: ${state.facilityId}`;
  } else {
    elements.facilityId.textContent = "該当する施設がありません。";
  }
}

/** 都道府県・施設選択を初期化し、研究上よく使う岡山県を初期表示する。 */
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

/** 都道府県変更時に施設候補とキャンバス表示を切り替える。 */
function changePrefecture() {
  state.selectedUid = null;
  renderFacilityOptions(elements.prefectureSelect.value);
  render();
}

/** 施設変更時に対応するレイアウトへ編集対象を切り替える。 */
function changeFacility() {
  state.facilityId = elements.facilitySelect.value;
  state.selectedUid = null;
  state.backgroundEdit = false;
  ensureLayout(state.facilityId);
  elements.facilityId.textContent = `facilityId: ${state.facilityId}`;
  render();
}

/** キャンバス寸法とメートル換算係数を現在施設のレイアウトへ保存する。 */
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

elements.canvas.addEventListener("click", (event) => {
  if (state.backgroundEdit || event.target.closest(".map-object")) {
    return;
  }
  state.selectedUid = null;
  render();
});
elements.canvas.addEventListener("pointerdown", (event) => {
  if (event.target === elements.canvas || event.target.closest(".satellite-layer")) {
    startBackgroundDrag(event);
  }
});
elements.canvas.addEventListener("pointermove", (event) => {
  moveBackgroundDrag(event);
  moveResize(event);
  moveDrag(event);
});
elements.canvas.addEventListener("pointerup", (event) => {
  if (endBackgroundDrag(event)) {
    return;
  }
  if (endResize(event)) {
    return;
  }
  endDrag(event);
});
elements.canvas.addEventListener("pointercancel", (event) => {
  if (endBackgroundDrag(event)) {
    return;
  }
  if (endResize(event)) {
    return;
  }
  endDrag(event);
});
elements.canvas.addEventListener("wheel", (event) => {
  if (!state.backgroundEdit) {
    return;
  }
  event.preventDefault();
  changeBackgroundZoom(event.deltaY < 0 ? 1 : -1);
}, { passive: false });

document.querySelector("#cloud-login-button").addEventListener("click", () => void remoteLogin());
document.querySelector("#cloud-sync-button").addEventListener("click", () => void syncCurrentLayout());
document.querySelector("#cloud-load-button").addEventListener("click", () => void loadRemoteLayouts());
document.querySelector("#cloud-logout-button").addEventListener("click", remoteLogout);
document.querySelector("#background-enable-button").addEventListener("click", enableBackground);
document.querySelector("#background-edit-button").addEventListener("click", toggleBackgroundEdit);
document.querySelector("#background-zoom-in-button").addEventListener("click", () => changeBackgroundZoom(1));
document.querySelector("#background-zoom-out-button").addEventListener("click", () => changeBackgroundZoom(-1));
document.querySelector("#apply-background-button").addEventListener("click", applyBackgroundSettings);
document.querySelector("#current-location-background-button").addEventListener("click", useCurrentLocationForBackground);
elements.backgroundOpacity.addEventListener("input", () => {
  const layout = getCurrentLayout();
  if (layout?.background?.type === "gsi-seamlessphoto") {
    layout.background.opacity = Number(elements.backgroundOpacity.value);
    const layer = elements.canvas.querySelector(".satellite-layer");
    if (layer) {
      layer.style.opacity = String(layout.background.opacity);
    }
    saveLocal();
  }
});
elements.prefectureSelect.addEventListener("change", changePrefecture);
elements.facilitySelect.addEventListener("change", changeFacility);
[elements.name, elements.x, elements.y, elements.rotation, elements.width, elements.height,
  elements.roadDirection, elements.parkingAccessType,
  elements.spaceType, elements.spaceStatus, elements.entranceType, elements.publicAccess,
  elements.wheelchairAccessible, elements.guideTarget, elements.buildingId].forEach((control) => {
  control.addEventListener("change", updateSelectedFromForm);
});

document.querySelectorAll("[data-adjacent-direction]").forEach((button) => {
  button.addEventListener("click", () => createAdjacentSpaces(button.dataset.adjacentDirection));
});
document.querySelector("#rotate-left-button").addEventListener("click", () => rotateSelected(-90));
document.querySelector("#rotate-right-button").addEventListener("click", () => rotateSelected(90));
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
  if (event.target.matches("input, select, textarea")) {
    return;
  }
  if (event.key === "Escape" && state.backgroundEdit) {
    toggleBackgroundEdit();
    return;
  }
  if (event.key === "Delete" || event.key === "Backspace") {
    deleteSelected();
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") {
    event.preventDefault();
    duplicateSelected();
    return;
  }
  const item = getSelectedObject();
  if (!item || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
    return;
  }
  event.preventDefault();
  const step = event.shiftKey ? 10 : 1;
  if (event.key === "ArrowLeft") item.x -= step;
  if (event.key === "ArrowRight") item.x += step;
  if (event.key === "ArrowUp") item.y -= step;
  if (event.key === "ArrowDown") item.y += step;
  item.x = Math.max(0, Math.min(getCurrentLayout().canvas.width - (item.width ?? 34), item.x));
  item.y = Math.max(0, Math.min(getCurrentLayout().canvas.height - (item.height ?? 34), item.y));
  saveLocal();
  render();
});

restoreLocal();
restoreRemoteSession();
initializeTheme();
initializeFacilities();
render();
