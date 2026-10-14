"use strict";
/* 編集補助。施設ごとの履歴・実寸・一覧は既存の保存形式をそのまま使う。 */
window.ParkingEditor = (() => {
  const $=id=>document.getElementById(id);
  const histories=new Map();let restoring=false,pan=null,lastFacility=null;
  function snapshot(){return JSON.stringify(getCurrentLayout());}
  function history(){
    if(!histories.has(state.facilityId))histories.set(state.facilityId,{past:[],present:snapshot(),future:[]});
    return histories.get(state.facilityId);
  }
  function record(){
    if(restoring||!getCurrentLayout())return;
    const h=history(),next=snapshot();
    if(next===h.present)return;
    h.past.push(h.present);if(h.past.length>40)h.past.shift();h.present=next;h.future=[];
    updateHistory();
  }
  function travel(redo=false){
    const h=history(),source=redo?h.future:h.past,target=redo?h.past:h.future;
    if(!source.length)return;
    target.push(h.present);h.present=source.pop();restoring=true;
    state.layouts[state.facilityId]=JSON.parse(h.present);state.selectedUid=null;
    state.drag=state.resize=state.vertexDrag=null;
    saveLocal();restoring=false;render();
  }
  function updateHistory(){const h=history();$('undo-button').disabled=!h.past.length;$('redo-button').disabled=!h.future.length;}
  function refresh(){
    if(!getCurrentLayout())return;
    if(lastFacility!==state.facilityId){lastFacility=state.facilityId;requestAnimationFrame(fitObjects);}
    history();updateHistory();
    const layout=getCurrentLayout(),scale=getLayoutScale(layout),item=getSelectedObject();
    $('scale-summary').textContent=`1 px ≈ ${scale.toFixed(3)} m · ${layout.canvas.scaleSource==='photo'?'航空写真基準':'設定縮尺'}`;
    $('object-count').textContent=`${layout.objects.length} 個`;
    $('dimension-controls').hidden=!item;
    $('preset-size-button').hidden=item?.objectType!=='parkingSpace';
    if(item){$('width-meters').value=(item.width*scale).toFixed(2);$('height-meters').value=(item.height*scale).toFixed(2);}
    const list=$('object-list'),filter=$('object-search').value.trim().toLowerCase();list.replaceChildren();
    for(const obj of [...layout.objects].reverse()){
      const label=obj.objectType==='parkingSpace'?`${mapDisplay.spaceName(obj)} · ${getParkingSpaceLabel(obj.spaceType)}`:obj.name;
      if(filter&&!`${label} ${obj.uid}`.toLowerCase().includes(filter))continue;
      const button=document.createElement('button');button.type='button';button.textContent=label||obj.objectType;
      button.className='object-list-item';button.setAttribute('aria-pressed',String(obj.uid===state.selectedUid));
      button.addEventListener('click',()=>{state.selectedUid=obj.uid;state.editMode='move';render();focusSelected();});list.append(button);
    }
    $('pavement-settings').hidden=item?.objectType!=='pavementMarking';
    if(item?.objectType==='pavementMarking'){$('pavement-kind').value=item.pavementKind||'straight';$('pavement-color').value=item.markingColor||'#ffffff';}
  }
  function focusSelected(){
    const item=getSelectedObject();if(!item)return;
    const viewport=elements.canvasScroll;
    viewport.scrollLeft=(item.x+item.width/2)*state.viewScale-viewport.clientWidth/2+24;
    viewport.scrollTop=(item.y+item.height/2)*state.viewScale-viewport.clientHeight/2+24;
  }
  function setMeters(){
    const item=getSelectedObject();if(!item||isObjectLocked(item))return;
    const width=Number($('width-meters').value),height=Number($('height-meters').value);
    if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0){$('editor-message').textContent='幅・長さは正の数値で入力してください。';return;}
    const scale=getLayoutScale(getCurrentLayout());
    elements.width.value=String(width/scale);elements.height.value=String(height/scale);updateSelectedFromForm();
    refresh();
  }
  function calibrate(){
    const layout=getCurrentLayout(),scale=mapDisplay.metersPerPixel(layout.background);
    if(!scale){$('editor-message').textContent='先に航空写真を表示してください。';return;}
    layout.canvas.scaleMetersPerPixel=scale;layout.canvas.scaleSource='photo';
    saveLocal();render();$('editor-message').textContent='写真の縮尺を採用しました。既存の枠は移動せず、新しい枠から実寸で追加します。';
  }
  function resizePreset(){
    const item=getSelectedObject();if(item?.objectType!=='parkingSpace'||isObjectLocked(item))return;
    const preset=PARKING_SPACE_PRESETS[item.spaceType]||PARKING_SPACE_PRESETS.standard;
    $('width-meters').value=preset.widthMeters;$('height-meters').value=preset.lengthMeters;setMeters();
  }
  function fitObjects(){
    const objects=getCurrentLayout().objects;if(!objects.length){fitViewScale();return;}
    // 回転した四隅も範囲に含める。
    const points=objects.flatMap(o=>[[0,0],[o.width,0],[0,o.height],[o.width,o.height]].map(([x,y])=>objectLocalPointToGlobal(o,x,y)));
    const x=Math.min(...points.map(p=>p.x)),y=Math.min(...points.map(p=>p.y));
    const w=Math.max(...points.map(p=>p.x))-x,h=Math.max(...points.map(p=>p.y))-y;
    applyViewScale(Math.min((elements.canvasScroll.clientWidth-96)/Math.max(w,1),(elements.canvasScroll.clientHeight-96)/Math.max(h,1)));
    elements.canvasScroll.scrollLeft=x*state.viewScale-48;elements.canvasScroll.scrollTop=y*state.viewScale-48;
  }
  $('undo-button').addEventListener('click',()=>travel());$('redo-button').addEventListener('click',()=>travel(true));
  $('apply-meters-button').addEventListener('click',setMeters);$('preset-size-button').addEventListener('click',resizePreset);
  $('photo-scale-button').addEventListener('click',calibrate);$('fit-objects-button').addEventListener('click',fitObjects);
  $('object-search').addEventListener('input',refresh);
  for(const id of ['pavement-kind','pavement-color'])$(id).addEventListener('change',()=>{
    const item=getSelectedObject();if(item?.objectType!=='pavementMarking')return;
    item.pavementKind=$('pavement-kind').value;item.markingColor=$('pavement-color').value;item.name=mapDisplay.pavementNames[item.pavementKind];saveLocal();render();
  });
  const kind=$('pavement-kind'),add=$('new-pavement-kind');
  Object.entries(mapDisplay.pavementNames).forEach(([value,label])=>{kind.add(new Option(label,value));add.add(new Option(label,value));});
  $('add-pavement-button').addEventListener('click',()=>addObject('pavementMarking',{pavementKind:add.value}));
  // 施設検索は選択結果を明示し、入力だけで編集施設を変えない。
  $('facility-search').addEventListener('input',()=>{
    const query=$('facility-search').value.normalize('NFKC').trim().toLowerCase(),list=$('facility-results');list.replaceChildren();
    if(!query)return;
    const candidates=[getExperimentFacility(),...state.facilities].filter(f=>`${getFacilityDisplayName(f)} ${f.address||''}`.normalize('NFKC').toLowerCase().includes(query));
    for(const facility of candidates){const button=document.createElement('button');button.type='button';button.textContent=getFacilityDisplayName(facility);button.addEventListener('click',()=>{elements.prefectureSelect.value=facility.prefecture;renderFacilityOptions(facility.prefecture,facility.id);changeFacility();list.replaceChildren();$('facility-search').value='';});list.append(button);}
  });
  document.addEventListener('keydown',event=>{
    if(event.target.matches('input,textarea,select,[contenteditable="true"]'))return;
    const key=event.key.toLowerCase();
    if((event.ctrlKey||event.metaKey)&&(key==='z'||key==='y')){event.preventDefault();travel(key==='y'||event.shiftKey);}
    if(event.key==='Escape'){state.backgroundEdit=false;state.drag=state.resize=state.vertexDrag=null;setEditMode('move');}
  });
  // Spaceなしでも中ボタンで配置図を移動できる。写真の位置は変更しない。
  elements.canvasScroll.addEventListener('pointerdown',event=>{if(event.button!==1)return;event.preventDefault();pan={id:event.pointerId,x:event.clientX,y:event.clientY,left:elements.canvasScroll.scrollLeft,top:elements.canvasScroll.scrollTop};elements.canvasScroll.setPointerCapture(event.pointerId);});
  elements.canvasScroll.addEventListener('pointermove',event=>{if(!pan||pan.id!==event.pointerId)return;elements.canvasScroll.scrollLeft=pan.left-event.clientX+pan.x;elements.canvasScroll.scrollTop=pan.top-event.clientY+pan.y;});
  for(const name of ['pointerup','pointercancel'])elements.canvasScroll.addEventListener(name,()=>pan=null);
  // Ctrl/Cmd+ホイールは写真倍率ではなく表示倍率だけを変更。
  elements.canvasScroll.addEventListener('wheel',event=>{if(!event.ctrlKey&&!event.metaKey)return;event.preventDefault();event.stopPropagation();applyViewScale(state.viewScale*(event.deltaY<0?1.15:1/1.15),true);},{passive:false,capture:true});
  window.addEventListener('resize',()=>requestAnimationFrame(fitObjects));
  refresh();return {record,refresh,travel,calibrate,setMeters,fitObjects,resetHistory:()=>{histories.clear();lastFacility=null;}};
})();
