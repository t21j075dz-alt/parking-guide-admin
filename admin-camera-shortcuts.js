/* 管理者アプリ：カメラ関連の主操作を、常に見える編集画面へ集約する。
 * 駐車場配置・ログイン状態・監視設定は変更しない。 */
(() => {
  "use strict";
  const workspace=document.querySelector(".workspace");
  const heading=workspace?.querySelector(".workspace-head");
  if(!workspace||!heading)return;

  function make(tag,className,text) {
    const node=document.createElement(tag);
    if(className)node.className=className;
    if(text!==undefined)node.textContent=text;
    return node;
  }
  const strip=make("div","admin-camera-shortcuts");
  strip.setAttribute("aria-label","駐車場のカメラ操作");
  const summary=make("div","admin-camera-shortcuts-summary");
  const title=make("strong",null,"駐車場カメラ");
  const count=make("span",null,"区画数を確認中");
  count.id="admin-camera-space-count";
  summary.append(title,count);
  const actions=make("div","admin-camera-shortcuts-actions");
  const buttons=[
    ["alignment","カメラと地図を合わせる"],
    ["camera","カメラの写真を見る"],
    ["monitor","空き状況を確認"],
  ];
  const names={
    en:["Match camera & map","View camera photo","Check occupancy"],
    ja:["カメラと地図を合わせる","カメラの写真を見る","空き状況を確認"],
  };
  function openToolsPanel(id) {
    const tools=document.querySelector("#admin-tools-panel");
    const target=document.getElementById(id);
    if(!tools||!target)return;
    const toggle=document.querySelector("#admin-tools-toggle");
    if(document.body.dataset.adminToolsOpen!=="true")toggle?.click();
    if(target.tagName==="DETAILS")target.open=true;
    target.scrollIntoView?.({block:"nearest",behavior:"auto"});
    target.querySelector("summary")?.focus?.({preventScroll:true});
  }
  for(const [i,[kind,label]] of buttons.entries()) {
    const button=make("button","admin-camera-shortcut",label);
    button.type="button";
    button.dataset.action=kind;
    if(kind==="alignment"){
      button.classList.add("is-primary");
      button.addEventListener("click",()=>document.dispatchEvent(
        new Event("parking:open-camera-alignment")));
    } else {
      button.addEventListener("click",()=>openToolsPanel(
        kind==="camera"?"camera-monitor":"live-monitor-panel"));
    }
    actions.append(button);
  }
  strip.append(summary,actions);
  heading.after(strip);

  function updateCount(){
    const current=typeof getCurrentLayout==="function"?getCurrentLayout():null;
    const items=Array.isArray(current?.objects)?current.objects:[];
    const num=items.filter(item=>item.objectType==="parkingSpace").length;
    count.textContent=num===0?"駐車枠：未登録":"駐車枠："+num+"区画";
    strip.dataset.hasSpaces=String(num>0);
    summary.title="この施設の管理マップに登録された駐車枠の数です。YOLOによる確認済み数ではありません。";
  }
  const canvas=document.getElementById("map-canvas");
  if(canvas)new MutationObserver(updateCount).observe(canvas,{childList:true});
  document.getElementById("facility-select")?.addEventListener("change",updateCount);
  document.getElementById("prefecture-select")?.addEventListener("change",updateCount);

  function syncLanguage(){
    const english=document.documentElement.lang.toLowerCase().startsWith("en");
    const labels=english?names.en:names.ja;
    title.textContent=english?"Parking camera":"駐車場カメラ";
    actions.querySelectorAll("button").forEach((button,i)=>button.textContent=labels[i]);
    updateCount();
  }
  const htmlObserver=new MutationObserver(syncLanguage);
  htmlObserver.observe(document.documentElement,{attributes:true,attributeFilter:["lang"]});
  syncLanguage();
})();
