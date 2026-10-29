/* 施設内の店舗を既存レイアウトへ保存。IDは改名しても変更しない。 */
(() => {
  const host=document.querySelector("#camera-monitor");if(!host)return;
  const trigger=document.createElement("button");trigger.type="button";trigger.textContent="施設内の店舗を管理";host.after(trigger);
  const dialog=document.createElement("dialog");dialog.className="camera-card facility-dialog";
  dialog.innerHTML=`<h2>施設内の店舗を管理</h2><button type="button" id="tenant-close">閉じる</button><p>店舗名と案内先の建物を設定します。営業時間は「営業時間・休業・共用区画」から店舗ごとに登録できます。</p><div id="tenant-rows"></div><button type="button" id="tenant-add">店舗を追加</button><button type="button" id="tenant-save">店舗一覧を保存</button><p role="status" id="tenant-status"></p>`;
  document.body.append(dialog);let draft=[],facilityId="";
  const q=id=>dialog.querySelector("#"+id);
  function render(){q("tenant-rows").replaceChildren();for(const destination of draft){
    const row=document.createElement("fieldset");const legend=document.createElement("legend");legend.textContent=destination.name||"新しい店舗";row.append(legend);
    for(const [key,label] of [["name","店舗名"],["nameEn","英語の店舗名"],["buildingId","建物ID（配置図と同じ名前）"],["sourceUrl","確認元の公式URL"]]){
      const wrapper=document.createElement("label");wrapper.textContent=label;const input=document.createElement("input");input.value=destination[key]||"";input.maxLength=key==="sourceUrl"?500:100;
      input.oninput=()=>{destination[key]=input.value.trim();};wrapper.append(input);row.append(wrapper);
    }
    const remove=document.createElement("button");remove.type="button";remove.textContent="この店舗を削除";remove.onclick=()=>{draft=draft.filter(d=>d.id!==destination.id);render();};row.append(remove);q("tenant-rows").append(row);
  }}
  trigger.onclick=()=>{facilityId=state.facilityId;draft=structuredClone(getAdminDestinations());q("tenant-status").textContent="";render();dialog.showModal();};
  q("tenant-close").onclick=()=>dialog.close();
  q("tenant-add").onclick=()=>{draft.push({id:"tenant_"+crypto.randomUUID(),name:"",buildingId:""});render();};
  q("tenant-save").onclick=()=>{
    if(facilityId!==state.facilityId){q("tenant-status").textContent="施設が変わりました。開き直してください。";return;}
    if(draft.some(d=>!d.name||!d.buildingId||d.sourceUrl&&!/^https:\/\//.test(d.sourceUrl))||new Set(draft.map(d=>d.id)).size!==draft.length){q("tenant-status").textContent="店舗名・建物ID・公式URLの形式を確認してください。";return;}
    getCurrentLayout().destinations=structuredClone(draft);saveLocal();updateBuildingIdOptions();q("tenant-status").textContent="店舗一覧を端末に保存しました。管理者ログイン中はクラウド保存後に店舗名の音声を自動で生成待ちへ登録します。";
  };
})();
