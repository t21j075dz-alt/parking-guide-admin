/* 既存の保存・履歴と同じ経路で営業情報、共用グループを編集する。 */
(() => {
  const host=document.querySelector("#camera-monitor");if(!host)return;
  const panel=document.createElement("dialog");panel.className="camera-card facility-dialog";
  panel.innerHTML=`<h2>営業時間・休業・共用区画</h2><button id="close-facility-editor" type="button">閉じる</button>
    <label>営業時間を設定する対象<select id="operation-scope"><option value="">施設全体</option></select></label>
    <label>営業時間の表示<input id="facility-hours-label" maxlength="100" placeholder="例：9:00–21:00"></label>
    <label><input id="facility-closed" type="checkbox">休業中（区画を案内しない）</label>
    <label><input id="hours-enabled" type="checkbox">曜日ごとの営業時間で「休」「閉」を自動表示</label>
    <div id="weekly-hours"></div>
    <p>終了が開始より早い場合は翌日まで営業。同じ時刻なら24時間営業です。</p>
    <button id="save-facility-operation" type="button">営業時間を保存</button>
    <hr><label>選択した区画の共用グループ<input id="space-shared-group" maxlength="64" placeholder="例：shared-A"></label>
    <p>大型枠と、その中の普通車枠に同じ名前を設定します。いずれかが使用中・未確認の場合は、グループ全体へ案内しません。</p>
    <button id="save-shared-group" type="button">選択区画に設定</button>
    <p role="status" id="facility-editor-status"></p><p id="facility-open-status"></p>`;
  const weekdays=["日曜日","月曜日","火曜日","水曜日","木曜日","金曜日","土曜日"];
  weekdays.forEach((name,day)=>{
    const row=document.createElement("div");row.className="weekly-row";
    row.innerHTML=`<label><input type="checkbox" id="day-${day}">${name}</label><label>開始<input type="time" id="open-${day}" value="09:00"></label><label>終了<input type="time" id="close-${day}" value="21:00"></label>`;
    panel.querySelector("#weekly-hours").append(row);
  });
  const trigger=document.createElement("button");trigger.type="button";trigger.textContent="営業時間・休業・共用区画";
  host.after(trigger);document.body.append(panel);
  trigger.onclick=()=>{last="";load();panel.showModal();};
  panel.querySelector("#close-facility-editor").onclick=()=>panel.close();
  const q=id=>panel.querySelector("#"+id);let last="";
  function load(){const layout=getCurrentLayout();
    const destination=getAdminDestinations().find(d=>d.id===q("operation-scope").value);
    const operation=window.ParkingOperations.operating(destination?.operations || layout?.operations || getCurrentFacilityRecord()?.operations);
    q("facility-open-status").textContent=document.documentElement.lang==="en"
      ? (operation.unknown?"Hours not configured":operation.closureKind==="rest"?"Day off":operation.preOpening?"Closed · before opening (guidance available)":operation.closed?"Closed · outside opening hours":"Currently open")
      : (operation.unknown?"営業時間は未設定です":operation.closureKind==="rest"?"休：定休日・臨時休業":operation.preOpening?"閉：開店前（案内可能）":operation.closed?"閉：営業時間外":"現在は営業中です");const item=getSelectedObject();const key=state.facilityId+":"+(item?.uid||"")+":"+q("operation-scope").value+":"+getAdminDestinations().map(d=>d.id).join(",");if(key===last)return;last=key;
    const previous=q("operation-scope").value;q("operation-scope").replaceChildren(new Option("施設全体",""));
    for(const d of getAdminDestinations())q("operation-scope").add(new Option(d.name,d.id));
    q("operation-scope").value=previous;
    const op=destination?.operations || (!previous?(layout?.operations || getCurrentFacilityRecord()?.operations):null) || {};q("facility-hours-label").value=op.hoursLabel||"";q("facility-closed").checked=op.closed===true;
    q("hours-enabled").checked=!!op.weeklyHours;
    weekdays.forEach((_,day)=>{const ranges=op.weeklyHours?.[day];q("day-"+day).checked=!!ranges?.length;q("open-"+day).value=ranges?.[0]?.[0]||"09:00";q("close-"+day).value=ranges?.[0]?.[1]||"21:00";});q("space-shared-group").value=item?.sharedGroup||"";
    q("save-shared-group").disabled=item?.objectType!=="parkingSpace";
  }
  q("operation-scope").onchange=()=>{last="";load();};
  panel.addEventListener("toggle",()=>{last="";load();});setInterval(()=>{if(panel.open)load();},500);
  q("save-facility-operation").onclick=()=>{try {
    const hours=q("hours-enabled").checked?Object.fromEntries(weekdays.map((_,day)=>[String(day),q("day-"+day).checked?[[q("open-"+day).value,q("close-"+day).value]]:[]])):null;
    if(hours && Object.values(hours).some(ranges=>ranges.some(r=>r.some(t=>!/^([01]\d|2[0-3]):[0-5]\d$/.test(t))))) throw Error("営業時間を入力してください");
    const layout=getCurrentLayout();
    const scope=q("operation-scope").value;
    if(scope&&!Array.isArray(layout.destinations))layout.destinations=structuredClone(getAdminDestinations());
    const target=scope?layout.destinations.find(d=>d.id===scope):layout;
    if(!target)throw Error("設定対象の店舗を選択してください");
    // 管理者が変更した内容は公式確認済み情報と混同せず、手動設定として扱う。
    target.operations={hoursLabel:q("facility-hours-label").value.trim(),closed:q("facility-closed").checked,weeklyHours:hours,timeZone:"Asia/Tokyo",hoursVerification:"manual",notes:"管理画面から手動設定"};
    saveLocal();q("facility-editor-status").textContent="営業時間を保存しました（公式確認済みの日時・出典は手動設定に切り替わりました）";
  }catch(e){q("facility-editor-status").textContent="保存できません："+e.message;}};
  q("save-shared-group").onclick=()=>{const item=getSelectedObject();if(item?.objectType!=="parkingSpace")return;item.sharedGroup=q("space-shared-group").value.trim();saveLocal();q("facility-editor-status").textContent="共用グループを設定しました";};
})();
