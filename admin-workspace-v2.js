"use strict";
/*
 * 管理画面の作業スペース。
 * 既存の編集・保存処理は変更しない。DOMを移してもIDとイベントは保持する。
 * 折り畳み状態はこの端末のUI設定だけに保存し、施設データは変更しない。
 */
(() => {
  const body=document.body;
  const layout=document.querySelector(".admin-layout");
  const tools=document.querySelector(".left-panel");
  const inspector=document.querySelector(".right-panel");
  const workspace=document.querySelector(".workspace");
  const header=document.querySelector(".topbar");
  const actions=document.querySelector(".topbar-actions");
  const toolbar=document.querySelector(".editor-toolbar");
  if(!layout||!tools||!inspector||!workspace||!header||!actions||!toolbar)return;

  tools.id="admin-tools-panel";
  inspector.id="admin-settings-panel";

  // 施設の切り替えを常時表示。選択中の施設はサイドパネルを閉じても分かる。
  const chooser=tools.querySelector(":scope > section");
  const facilityStrip=document.createElement("div");
  facilityStrip.className="admin-facility-strip";
  facilityStrip.setAttribute("aria-label","編集対象の施設");
  if(chooser){
    chooser.classList.add("admin-facility-picker");
    facilityStrip.append(chooser);
    layout.before(facilityStrip);
  }

  // 上部には「元に戻す・やり直す・端末保存」だけを常時配置。
  // テーマ・言語・書き出し・読み込みは必要なときだけ展開する。
  const more=document.createElement("details");
  more.className="admin-header-more";
  const moreSummary=document.createElement("summary");
  moreSummary.textContent="その他の操作";
  moreSummary.setAttribute("aria-label","テーマ・言語・バックアップ操作を開く");
  const moreInner=document.createElement("div");
  moreInner.className="admin-header-more-content";
  for(const id of ["language-button","theme-button","export-json-button","export-js-button"]){
    const node=document.getElementById(id);
    if(node)moreInner.append(node);
  }
  const importLabel=actions.querySelector(".file-button");
  if(importLabel)moreInner.append(importLabel);
  more.append(moreSummary,moreInner);
  actions.append(more);

  const statusRow=document.createElement("div");
  statusRow.className="admin-header-status";
  const localStatus=document.getElementById("local-save-status");
  if(localStatus)statusRow.append(localStatus);
  const cloudSummary=document.createElement("span");
  cloudSummary.id="admin-cloud-summary";
  cloudSummary.textContent="クラウド状態を確認中";
  cloudSummary.title="クラウドの状態は追加ツール内の「ユーザーアプリへ自動反映」で確認できます";
  statusRow.append(cloudSummary);
  header.append(statusRow);
  const cloudStatus=document.getElementById("cloud-sync-status");
  const syncCloud=()=>{
    const value=cloudStatus?.textContent?.replace(/\s+/g," ").trim()||"クラウド連携：未設定";
    cloudSummary.textContent=value;
    cloudSummary.title=value;
  };
  if(cloudStatus){
    new MutationObserver(syncCloud).observe(cloudStatus,{childList:true,characterData:true,subtree:true});
  }
  syncCloud();

  // マップを広く使うため、キャンバス寸法入力は必要なときだけ表示。
  const dimensions=document.querySelector(".workspace-head .canvas-settings");
  if(dimensions){
    const details=document.createElement("details");
    details.className="admin-canvas-dimensions";
    const summary=document.createElement("summary");
    summary.textContent="図面の寸法";
    details.append(summary);
    dimensions.replaceWith(details);
    details.append(dimensions);
  }

  const head=document.querySelector(".workspace-head");
  const panelActions=document.createElement("div");
  panelActions.className="admin-panel-actions";
  panelActions.setAttribute("role","group");
  panelActions.setAttribute("aria-label","作業エリアの表示切り替え");
  const makeToggle=(id,label,controls)=>{
    const button=document.createElement("button");
    button.id=id;
    button.type="button";
    button.textContent=label;
    if(controls)button.setAttribute("aria-controls",controls);
    panelActions.append(button);
    return button;
  };
  const toolsToggle=makeToggle("admin-tools-toggle","追加ツール","admin-tools-panel");
  const inspectorToggle=makeToggle("admin-settings-toggle","選択中の設定","admin-settings-panel");
  const focusToggle=makeToggle("admin-focus-toggle","集中モード");
  head.prepend(panelActions);

  // 駐車枠の追加は、左ペインを開かずに配置図の上から操作できる。
  const originalType=document.getElementById("new-parking-space-type");
  const originalAdd=document.getElementById("add-parking-space-button");
  if(originalType&&originalAdd){
    const quick=document.createElement("div");
    quick.className="admin-quick-add";
    const quickLabel=document.createElement("label");
    quickLabel.setAttribute("for","admin-quick-space-type");
    quickLabel.textContent="駐車枠";
    const quickType=document.createElement("select");
    quickType.id="admin-quick-space-type";
    // 元の種類一覧を複製し、実際の追加処理は元のボタンに委譲する。
    quickType.innerHTML=originalType.innerHTML;
    quickType.value=originalType.value;
    const quickAdd=document.createElement("button");
    quickAdd.id="admin-quick-space-add";
    quickAdd.type="button";
    quickAdd.textContent="＋ 追加";
    quickAdd.addEventListener("click",()=>{
      originalType.value=quickType.value;
      originalType.dispatchEvent(new Event("change",{bubbles:true}));
      originalAdd.click();
    });
    originalType.addEventListener("change",()=>{quickType.value=originalType.value;});
    quick.append(quickLabel,quickType,quickAdd);
    toolbar.insertBefore(quick,toolbar.querySelector(".editor-zoom"));
  }

  // 頻度が低い回転・方眼・一括サイズ変更はまとめて格納する。
  const advanced=document.createElement("details");
  advanced.className="admin-extra-editing";
  const advancedSummary=document.createElement("summary");
  advancedSummary.textContent="回転・詳細";
  advanced.append(advancedSummary);
  for(const id of ["rotate-left-button","rotate-right-button"]){
    const button=document.getElementById(id);
    if(button)advanced.append(button);
  }
  const existingAdvanced=toolbar.querySelector(".editor-advanced");
  if(existingAdvanced)advanced.append(existingAdvanced);
  toolbar.append(advanced);

  // 区画線の調整や連続配置も折り畳める。入力値とイベントは移動後も保持する。
  function collapseSection(selector,title){
    const node=inspector.querySelector(selector);
    if(!node)return;
    const details=document.createElement("details");
    details.className="admin-inspector-extra";
    const summary=document.createElement("summary");
    summary.textContent=title;
    node.replaceWith(details);
    details.append(summary,node);
  }
  collapseSection(".parking-marking-settings","区画線の形・色・太さ");
  collapseSection(".adjacent-generator","同じ種類の枠を連続配置");

  // 左にたくさんある追加ツールは一括で開閉可能にする。
  const toolControls=document.createElement("div");
  toolControls.className="admin-tool-controls";
  const toolTitle=document.createElement("strong");
  toolTitle.textContent="追加するものを選択";
  const foldAll=document.createElement("button");
  foldAll.type="button";
  foldAll.textContent="すべて閉じる";
  foldAll.addEventListener("click",()=>{
    tools.querySelectorAll("details.palette-section, details.camera-card").forEach(d=>{d.open=false;});
  });
  toolControls.append(toolTitle,foldAll);
  tools.prepend(toolControls);

  const backdrop=document.createElement("button");
  backdrop.type="button";
  backdrop.className="admin-sidebar-backdrop";
  backdrop.setAttribute("aria-label","サイドパネルを閉じる");
  layout.append(backdrop);

  const storageKey="parking-admin-workspace-v1";
  const defaults={tools:false,settings:window.matchMedia("(min-width: 1200px)").matches};
  let saved={};
  try{saved=JSON.parse(localStorage.getItem(storageKey)||"{}")||{};}catch{}
  const desktop={
    tools:typeof saved.tools==="boolean"?saved.tools:defaults.tools,
    settings:typeof saved.settings==="boolean"?saved.settings:defaults.settings
  };
  let mobilePanel=null;
  let focus=false;
  const media=window.matchMedia("(max-width: 900px)");
  const isMobile=()=>media.matches;
  function visible(side){
    if(focus)return false;
    return isMobile()?mobilePanel===side:desktop[side];
  }
  function apply(){
    const showTools=visible("tools"),showSettings=visible("settings");
    body.dataset.adminToolsOpen=String(showTools);
    body.dataset.adminSettingsOpen=String(showSettings);
    body.dataset.adminFocus=String(focus);
    body.dataset.adminOverlay=String(isMobile()&&(showTools||showSettings));
    toolsToggle.setAttribute("aria-expanded",String(showTools));
    inspectorToggle.setAttribute("aria-expanded",String(showSettings));
    toolsToggle.setAttribute("aria-pressed",String(showTools));
    inspectorToggle.setAttribute("aria-pressed",String(showSettings));
    focusToggle.setAttribute("aria-pressed",String(focus));
    toolsToggle.textContent=showTools?"追加ツールを閉じる":"追加ツール";
    inspectorToggle.textContent=showSettings?"設定を閉じる":"選択中の設定";
    focusToggle.textContent=focus?"通常表示に戻す":"集中モード";
    tools.inert=!showTools;
    inspector.inert=!showSettings;
  }
  function persist(){
    try{localStorage.setItem(storageKey,JSON.stringify(desktop));}catch{}
  }
  function toggle(side){
    if(focus)focus=false;
    if(isMobile())mobilePanel=mobilePanel===side?null:side;
    else{desktop[side]=!desktop[side];persist();}
    apply();
  }
  toolsToggle.addEventListener("click",()=>toggle("tools"));
  inspectorToggle.addEventListener("click",()=>toggle("settings"));
  focusToggle.addEventListener("click",()=>{focus=!focus;mobilePanel=null;apply();});
  backdrop.addEventListener("click",()=>{mobilePanel=null;apply();});
  const resize=()=>{mobilePanel=null;apply();};
  media.addEventListener?.("change",resize);
  document.addEventListener("keydown",event=>{
    if(event.key!=="Escape"||!isMobile()||!mobilePanel)return;
    if(document.querySelector('dialog[open]'))return;
    event.preventDefault();
    const previous=mobilePanel;
    mobilePanel=null;
    apply();
    (previous==="tools"?toolsToggle:inspectorToggle).focus();
  });

  // 集中モードでも、選択中の区画が分かる小さな表示を残す。
  const selected=document.createElement("span");
  selected.id="admin-selection-summary";
  selected.setAttribute("aria-live","off");
  head.append(selected);
  function updateContext(){
    let item=null;
    try{if(typeof getSelectedObject==="function")item=getSelectedObject();}catch{}
    const label=item?(item.name||item.uid||"選択中の図形"):"未選択";
    selected.textContent=item?"選択中："+label:"区画・建物をクリックして選択";
    selected.title=selected.textContent;
  }
  let scheduled=false;
  function scheduleContext(){
    if(scheduled)return;
    scheduled=true;
    requestAnimationFrame(()=>{scheduled=false;updateContext();});
  }
  for(const name of ["pointerup","click","change","keyup"]){
    document.addEventListener(name,scheduleContext);
  }
  setInterval(()=>{if(!document.hidden)updateContext();},1500);

  // 初期化が完了するまで旧UIを保ち、完了時だけ新レイアウトへ移行する。
  body.classList.add("admin-layout-ready");
  apply();
  updateContext();
  window.ParkingAdminLayout={updateContext,showTools:()=>toggle("tools"),showSettings:()=>toggle("settings")};
})();
