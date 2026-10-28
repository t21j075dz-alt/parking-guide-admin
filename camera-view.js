/* 最新の静止画だけを表示。施設・認証切替時には前の画像を破棄する。 */
(() => {
  "use strict";
  const admin = document.querySelector("#camera-monitor");
  const panel = admin || document.querySelector("#facility-camera");
  if (!panel) return;
  let generation=0, lastId="", lastToken="", busy=false, lastFetch=0;
  const image=panel.querySelector("img"), status=panel.querySelector("[role=status]"), select=panel.querySelector("select");
  let rows=[];
  const english=()=>document.documentElement.lang==="en";
  const text=(ja,en)=>english()?en:ja;
  const current=()=>admin ? {id:state.facilityId,token:state.remoteAccessToken||""} : {id:state.selectedFacility?.id||"",token:""};
  const clear=()=>{image.hidden=true;image.removeAttribute("src");rows=[];select.replaceChildren();};
  function show() {
    const row=rows.find(r=>r.camera_id===select.value);
    const age=Date.now()-Date.parse(row?.captured_at);
    const maxAge=admin?30000:360000;
    if (!row || !Number.isFinite(age) || age>maxAge || age < -5000 || !/^data:image\/jpeg;base64,[A-Za-z0-9+/=]+$/.test(row.image_data)) {
      image.hidden=true;image.removeAttribute("src");
      status.textContent=text("現在の写真を確認できません", "Current photo unavailable");return;
    }
    if(image.getAttribute("src")!==row.image_data) image.src=row.image_data;image.hidden=false;
    status.textContent=text("撮影：", "Captured: ")+new Date(row.captured_at).toLocaleString(english()?"en-GB":"ja-JP")+text(admin?" · 5秒ごとに更新":" · 5分ごとに更新",admin?" · refreshes every 5 seconds":" · refreshes every 5 minutes");
  }
  async function refresh(force=false) {
    const {id,token}=current();
    if (id!==lastId || token!==lastToken) {generation++;lastId=id;lastToken=token;lastFetch=0;clear();}
    const screen=document.querySelector("#condition-screen");
    if (!id || document.hidden || (admin?!admin.open:screen?.hidden)) return;
    if(admin&&!token){clear();status.textContent=text("管理者ログインが必要です", "Administrator sign-in required");return;}
    show();
    if(busy || (!force && Date.now()-lastFetch<(admin?5000:300000))) return;
    const c=window.PARKING_REMOTE_CONFIG||{};
    if(!c.enabled || !/^https:\/\//.test(c.supabaseUrl||"")) return;
    busy=true;lastFetch=Date.now();const request=generation;
    try {
      const table=admin?"parking_camera_private":"parking_camera_public";
      const response=await fetch(c.supabaseUrl.replace(/\/$/,"")+"/rest/v1/"+table+"?facility_id=eq."+encodeURIComponent(id)+"&select=camera_id,captured_at,image_data&order=camera_id&limit=16",{
        headers:{apikey:c.publishableKey,...(token?{Authorization:"Bearer "+token}:{})},cache:"no-store",signal:AbortSignal.timeout(8000)});
      if(!response.ok)throw new Error("HTTP "+response.status);
      const data=await response.json();
      if(request!==generation || id!==current().id || token!==current().token)return;
      if(!Array.isArray(data))throw new Error("Unexpected camera data");
      const previous=select.value;rows=data;select.replaceChildren();
      for(const row of rows){const option=document.createElement("option");option.value=row.camera_id;option.textContent=row.camera_id;select.append(option);}
      if(rows.some(r=>r.camera_id===previous))select.value=previous;
      show();
    }catch {if(request===generation){clear();status.textContent=text("写真が未公開、または通信できません", "Photo unpublished or connection unavailable");}}
    finally{busy=false;}
  }
  if(admin) {
    const expand=document.createElement("button");expand.type="button";expand.textContent="写真を大きく表示";expand.className="secondary-button";panel.append(expand);
    const viewer=document.createElement("dialog");viewer.className="camera-viewer";
    const close=document.createElement("button");close.type="button";close.textContent="閉じる";
    const large=document.createElement("img");large.alt="駐車場のカメラ写真";
    viewer.append(close,large);document.body.append(viewer);close.onclick=()=>viewer.close();
    expand.onclick=()=>{if(!image.hidden){large.src=image.src;viewer.showModal();}};
    const sync=()=>{if(viewer.open){if(image.hidden){large.removeAttribute("src");viewer.close();}else if(large.src!==image.src)large.src=image.src;}};
    new MutationObserver(sync).observe(image,{attributes:true,attributeFilter:["src","hidden"]});
  }
  select.addEventListener("change",show);
  panel.querySelector("button").addEventListener("click",()=>void refresh(true));
  if(admin)admin.addEventListener("toggle",()=>void refresh(true));
  setInterval(()=>void refresh(),1000);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden){lastFetch=0;void refresh();}});
})();
