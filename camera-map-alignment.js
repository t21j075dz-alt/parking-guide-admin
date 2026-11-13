/* 管理マップ↔カメラ映像の初回位置合わせ。
 * 4〜24組の床面対応点で誤差を評価しながら区画を投影する。
 * 確認前にクラウド・YOLO設定を変更しない。
 */
(() => {
  "use strict";
  const core=window.ParkingCameraMapAlignment;
  const open=document.querySelector("#open-camera-map-alignment");
  const dialog=document.querySelector("#camera-map-alignment-dialog");
  if(!core||!open||!dialog)return;
  const get=id=>dialog.querySelector("#"+id);
  const map=get("alignment-map"), image=get("alignment-image"), overlay=get("alignment-camera-overlay");
  const cameraId=get("alignment-camera-id"), message=get("alignment-message");
  const resultLabel=get("alignment-result");
  const exportButton=get("alignment-export"), applyButton=get("alignment-project");
  const file=get("alignment-file"), confirmed=get("alignment-confirm-visual");
  const zoom=get("alignment-map-zoom"),steps=[...get("alignment-steps").children];
  const pointCount=get("alignment-point-count"),nextAction=get("alignment-next-action");
  const pointList=get("alignment-point-list"),quality=get("alignment-quality");
  const outlierCount=get("alignment-outlier-count");
  const editor=get("alignment-photo-editor"),methodSelect=get("alignment-zone-method");
  const slotSelect=get("alignment-slot-select"),drawZoneButton=get("alignment-draw-zone");
  const clearZoneButton=get("alignment-clear-zone"),editorHint=get("alignment-photo-editor-hint");
  const editorCount=get("alignment-photo-editor-count");
  const coverageSettings=get("alignment-coverage-settings"),coverageList=get("alignment-coverage-list");
  const facilityLabel=get("alignment-facility-label"),spaceCount=get("alignment-space-count");
  const photoInfo=get("alignment-image-info"),photoReady=get("alignment-photo-ready");
  const placeholder=get("alignment-image-placeholder"),markers=[...get("alignment-point-markers").children];
  const NS="http://www.w3.org/2000/svg";
  const memoryKey="parkingCameraMapAlignmentsV1";
  let mapPoints=[],imagePoints=[],projected=null,currentFacility="",fileUrl=null;
  let layoutChanged=false, showWholeMap=false, exported=false;
  let automatic=null,manualZones={},activeUid="",pendingCorners=null,drag=null;

  function notify(text){message.textContent=text;}
  function svg(tag,attrs,text){
    const node=document.createElementNS(NS,tag);
    for(const [key,value] of Object.entries(attrs||{}))node.setAttribute(key,String(value));
    if(text!==undefined)node.textContent=String(text);
    return node;
  }
  function layout(){
    if(typeof state==="undefined"||typeof getCurrentLayout!=="function")return null;
    if(state.facilityId!==currentFacility)return null;
    return getCurrentLayout();
  }
  function saved(){
    try{return JSON.parse(localStorage.getItem(memoryKey)||"{}")||{};}catch{return {};}
  }
  function storageId(){return currentFacility+"|"+cameraId.value.trim();}
  function editorMode(){return methodSelect.value;}
  function enabledManual(){return currentFacility==="nikko-test-001"&&editorMode()!=="auto";}
  function usableSlots(){
    return (layout()?.objects||[]).filter(o=>o.objectType==="parkingSpace");
  }
  function currentSlot(){return usableSlots().find(o=>o.uid===activeUid)||null;}
  function showEditor(){
    editor.hidden=currentFacility!=="nikko-test-001";
    if(editor.hidden)return;
    slotSelect.replaceChildren();
    for(const obj of usableSlots()){
      const item=document.createElement("option");
      item.value=obj.uid;
      item.textContent=String(obj.spaceGroup||"")+
        " "+String(obj.spaceNumber||obj.name||obj.uid)+" ("+obj.uid+")"+
        (obj.cameraCoverage==="outside"?"・画角外":"");
      slotSelect.append(item);
    }
    if(!activeUid||!usableSlots().some(o=>o.uid===activeUid))
      activeUid=usableSlots()[0]?.uid||"";
    slotSelect.value=activeUid;
    updateEditorStatus();
  }
  function updateEditorStatus(){
    if(editor.hidden)return;
    const total=Object.keys(manualZones).length;
    editorCount.textContent="個別補正 "+total+"件";
    const slot=currentSlot(),mode=editorMode();
    drawZoneButton.disabled=mode==="auto"||!slot||slot.cameraCoverage==="outside"||
      image.hidden||!image.naturalWidth;
    clearZoneButton.disabled=!slot||!Object.hasOwn(manualZones,slot.uid);
    editorHint.textContent=pendingCorners
      ? "写真で"+activeUid+"の四隅を選択中（"+pendingCorners.length+"/4）。白線の角を順にクリックしてください。"
      : mode==="auto"
        ? "全体の位置合わせをします。区画ごとの修正には「ずれた枠だけ補正」を選んでください。"
        : !slot ? "管理マップに駐車枠を登録してください。"
        : slot.cameraCoverage==="outside" ? "この区画は画角外に指定済みです。修正する場合は範囲外指定を解除してください。"
        : Object.hasOwn(manualZones,slot.uid)
          ? "この区画は写真から補正済みです。四隅の丸をドラッグして微調整できます。"
          : "写真上の緑色の枠を選ぶか、「この枠の四隅を写真で指定」を押してください。";
  }
  function materialize(){
    const mode=editorMode();
    if(mode==="auto")return automatic;
    if(mode==="manual"){
      if(!Object.keys(manualZones).length)return null;
      return core.composeCameraZones(layout(),null,manualZones);
    }
    if(!automatic&&!Object.keys(manualZones).length)return null;
    return core.composeCameraZones(layout(),automatic,manualZones);
  }
  function syncZones(){
    try{projected=materialize();}
    catch(error){projected=null;notify("写真の登録を見直してください: "+error.message);}
    confirmed.checked=false;exported=false;
  }
  function persistDraft(){
    const current=layout();
    if(!current)return;
    try{
      const all=saved();
      all[storageId()]={map_points:mapPoints,image_points:imagePoints,
        manual_zones:manualZones,mode:editorMode(),
        canvas:{width:Number(current.canvas.width),height:Number(current.canvas.height)},
        layout_signature:core.layoutSignature(current),
        image_ratio:image.naturalWidth&&image.naturalHeight
          ? image.naturalWidth/image.naturalHeight
          : all[storageId()]?.image_ratio||null};
      localStorage.setItem(memoryKey,JSON.stringify(all));
    }catch{notify("端末に一時保存できません。最後に設定JSONを書き出してください。");}
  }

  function refresh(){
    const hasPhoto=!image.hidden&&image.naturalWidth>0;
    const paired=Math.min(mapPoints.length,imagePoints.length);
    const completed=paired>=4&&mapPoints.length===imagePoints.length;
    const bad=projected?.alignmentDiagnostics?.outlierIndices?.length||0;
    applyButton.disabled=!hasPhoto||!completed;
    exportButton.disabled=!projected||!confirmed.checked||!hasPhoto||bad>0||Boolean(pendingCorners);
    confirmed.disabled=!projected||!hasPhoto||bad>0||Boolean(pendingCorners);
    pointCount.textContent="対応点 "+paired+" / 最大"+core.MAX_PAIRS+"組";
    nextAction.textContent=!hasPhoto?"先にカメラ写真を読み込んでください"
      : projected
        ? bad ? "誤差の大きい"+bad+"点を削除・選び直してください"
          : confirmed.checked ? "確認済みです。設定JSONを保存できます"
          : "緑の枠を確認。ずれが残る場合は追加点を指定できます"
        : mapPoints.length>imagePoints.length ? "右の写真で同じ場所の点"+(paired+1)+"を選択"
        : completed ? "全区画の位置を自動計算できます。追加点も選択できます"
        : "左のマップで点"+(paired+1)+"を選択";
    markers.forEach((node,index)=>{
      node.classList.toggle("is-complete",index<paired);
      node.classList.toggle("is-current",index===paired&&paired<4);
    });
    const active=!hasPhoto?0:!projected?(completed?2:1):!confirmed.checked?2:3;
    steps.forEach((node,index)=>{
      node.classList.toggle("is-current",index===active);
      node.classList.toggle("is-complete",index<active||(index===3&&exported));
      if(index===active)node.setAttribute("aria-current","step");
      else node.removeAttribute("aria-current");
    });
    photoInfo.textContent=hasPhoto
      ? "写真 "+image.naturalWidth+" × "+image.naturalHeight+" px" : "カメラ写真なし";
    photoReady.textContent=hasPhoto?"写真を表示中":"未選択";
    photoReady.dataset.ready=String(hasPhoto);
    placeholder.hidden=hasPhoto;
    const current=layout();
    spaceCount.textContent=current
      ? "登録区画 "+(current.objects||[]).filter(item=>item.objectType==="parkingSpace").length+"件"
      : "区画なし";
    resultLabel.textContent=projected
      ? currentFacility==="nikko-test-001"
        ? "録画の判定対象 "+projected.space_uids.length+"区画／対象外 "+projected.excluded_space_uids.length+"区画。映像内の全区画が合っているか確認してください。"
        : projected.space_uids.length+"区画の位置を計算しました。映像上の枠が一致しているか確認してください。"
      : "区画位置は未確定です。既存の駐車状態は変更されません。";
    updateEditorStatus();
  }
  function pointFromClick(event,element){
    const matrix=element.getScreenCTM();
    if(!matrix)throw Error("画像を表示してから点を選んでください。");
    const pt=element.createSVGPoint();pt.x=event.clientX;pt.y=event.clientY;
    const clicked=pt.matrixTransform(matrix.inverse()),box=element.viewBox.baseVal;
    if(!box.width||!box.height)throw Error("画像の表示サイズが取得できません。");
    // 描画倍率に関係なくマップの論理キャンバス全体へ正規化する。
    const current=layout();
    const x=element===map?clicked.x/Number(current?.canvas?.width):clicked.x;
    const y=element===map?clicked.y/Number(current?.canvas?.height):clicked.y;
    if(x<0||x>1||y<0||y>1)throw Error("画像内の点を選んでください。");
    return [x,y];
  }
  /** 日光専用。監視範囲外を指定しても駐車枠そのものは消去しない。 */
  function renderCoverageChoices(){
    coverageList.replaceChildren();
    coverageSettings.hidden=currentFacility!=="nikko-test-001";
    if(coverageSettings.hidden)return;
    const current=layout();
    for(const item of (current?.objects||[]).filter(obj=>obj.objectType==="parkingSpace")){
      const label=document.createElement("label");
      label.className="alignment-coverage-option";
      const box=document.createElement("input");
      box.type="checkbox";
      box.checked=item.cameraCoverage==="outside";
      const name=document.createElement("span");
      name.textContent=String(item.spaceNumber||item.name||item.uid)+"（"+item.uid+"）";
      label.append(box,name);
      coverageList.append(label);
      box.addEventListener("change",()=>{
        if(item.cameraCoverage==="outside" && !box.checked)delete item.cameraCoverage;
        else if(box.checked)item.cameraCoverage="outside";
        if(typeof saveLocal==="function")saveLocal();
        projected=null;confirmed.checked=false;exported=false;
        draw();
        notify("画角外の設定を保存しました。区画を自動計算し直し、映像と一致するか確認してください。");
      });
    }
  }

  /** 点ごとの投影誤差を実画像のpxで表示。誤った組を個別削除できる。 */
  function renderPointReview(){
    pointList.replaceChildren();
    const info=projected?.alignmentDiagnostics;
    const bad=new Set(info?.outlierIndices||[]);
    const paired=Math.min(mapPoints.length,imagePoints.length);
    const px=([dx,dy])=>Math.hypot(dx*image.naturalWidth,dy*image.naturalHeight);
    if(info){
      const rms=Math.sqrt(info.inlierIndices.reduce((sum,i)=>
        sum+px(info.residualVectors[i])**2,0)/Math.max(1,info.inlierIndices.length));
      quality.textContent=info.pairCount===4
        ? "4点から計算しました。点を追加すると全体のずれも評価できます。"
        : "採用"+info.inlierIndices.length+"点・誤差大"+bad.size+
          "点・平均誤差（RMS）"+rms.toFixed(1)+"px"+
          (bad.size?"。赤い点は削除・選び直してください。":"。区画のずれを目視確認してください。");
      quality.dataset.state=bad.size?"warning":"ready";
    }else{
      quality.textContent=paired<4
        ? "最低4組。6〜12組を駐車場全体に散らすと誤差を検証しやすくなります。"
        : "登録済み"+paired+"組。自動計算すると点ごとのずれを確認できます。";
      delete quality.dataset.state;
    }
    outlierCount.textContent=bad.size?"（誤差大 "+bad.size+"点）":"（"+paired+"組）";
    for(let i=0;i<paired;i++){
      const li=document.createElement("li");
      li.className="alignment-point-item";
      if(bad.has(i))li.dataset.outlier="true";
      const label=document.createElement("span");
      label.textContent="点"+(i+1)+(info
        ? " · "+(bad.has(i)?"誤差大 ":"ずれ ")+px(info.residualVectors[i]).toFixed(1)+"px"
        : " · 地図・写真登録済み");
      const remove=document.createElement("button");
      remove.type="button";remove.className="secondary-button";remove.textContent="削除";
      remove.setAttribute("aria-label","位置合わせ点"+(i+1)+"を削除");
      remove.addEventListener("click",()=>{
        mapPoints.splice(i,1);imagePoints.splice(i,1);
        projected=null;confirmed.checked=false;exported=false;
        draw();notify("点"+(i+1)+"を削除しました。必要なら選び直して再計算してください。");
      });
      li.append(label,remove);pointList.append(li);
    }
  }

  function draw(){
    const current=layout();
    map.replaceChildren();overlay.replaceChildren();
    if(!current)return;
    const width=Number(current.canvas?.width)||1,height=Number(current.canvas?.height)||1;
    const viewport=showWholeMap?{x:0,y:0,width,height}:core.parkingViewport(current);
    map.setAttribute("viewBox",[viewport.x,viewport.y,viewport.width,viewport.height].join(" "));
    zoom.textContent=showWholeMap?"区画を大きく表示":"地図全体を見る";
    zoom.setAttribute("aria-pressed",String(showWholeMap));
    map.append(svg("rect",{x:0,y:0,width,height,fill:"#e9eef2"}));
    for(const item of current.objects||[]){
      if(item.objectType!=="parkingSpace")continue;
      try{
        map.append(svg("polygon",{
          points:core.parkingCorners(item).map(p=>p.join(",")).join(" "),
          fill:item.cameraCoverage==="outside"?"#acb4c0":"#92d9c3",
          stroke:item.cameraCoverage==="outside"?"#606a7a":"#177a61","stroke-width":Math.max(1,width/800)
        }));
        const centerX=Number(item.x)+Number(item.width)/2;
        const centerY=Number(item.y)+Number(item.height)/2;
        const title=String(item.spaceNumber||item.uid).replace(/^0+/,"")||"0";
        map.append(svg("text",{x:centerX,y:centerY,fill:"#174b3e",
          "text-anchor":"middle","dominant-baseline":"central","font-size":Math.max(9,width/90)},title));
      }catch{}
    }
    mapPoints.forEach((p,i)=>{
      const x=p[0]*width,y=p[1]*height;
      const bad=projected?.alignmentDiagnostics?.outlierIndices?.includes(i);
      map.append(svg("circle",{cx:x,cy:y,r:Math.max(3,width/160),fill:bad?"#dc3545":"#e07121",stroke:"white","stroke-width":Math.max(1,width/1000)}));
      map.append(svg("text",{x:x+width/95,y:y-height/95,fill:"#a33e10","font-size":Math.max(12,width/65),"font-weight":"bold"},i+1));
    });
    overlay.setAttribute("viewBox","0 0 1 1");
    if(projected)for(const [uid,polygon] of Object.entries(projected.space_zones)){
      overlay.append(svg("polygon",{
        points:polygon.map(p=>p.join(",")).join(" "),
        fill:"rgba(57,196,139,0.20)",stroke:"#2de6a7","stroke-width":.003
      }));
      const center=polygon.reduce((s,p)=>[s[0]+p[0]/4,s[1]+p[1]/4],[0,0]);
      overlay.append(svg("text",{x:center[0],y:center[1],fill:"#ffffff",stroke:"#203f35",
        "stroke-width":.0003,"paint-order":"stroke","text-anchor":"middle",
        "font-size":.018,"font-weight":"bold"},uid.replace(/^space_0*/,"")));
    }
    imagePoints.forEach((p,i)=>{
      const bad=projected?.alignmentDiagnostics?.outlierIndices?.includes(i);
      overlay.append(svg("circle",{cx:p[0],cy:p[1],r:.009,fill:bad?"#dc3545":"#ffbf66",stroke:"white","stroke-width":.002}));
      overlay.append(svg("text",{x:p[0]+.012,y:p[1]-.012,fill:"#fff","font-size":.025,"font-weight":"bold"},i+1));
    });
    if(mapPoints.length<4||mapPoints.length!==imagePoints.length){
      const n=Math.min(mapPoints.length,imagePoints.length)+1;
      notify(mapPoints.length>imagePoints.length
        ? "② カメラ映像で、マップの点"+n+"と同じ床面上の位置を選んでください。"
        : "① マップで対応点"+n+"を選んでください。離れた白線の角などを選びます。");
    }
    renderPointReview();
    refresh();
  }
  function generateVisibleZones(){
    return core.generateZones(layout(),mapPoints,imagePoints,
      {skipOutsideFrame:currentFacility==="nikko-test-001"});
  }
  function reset(){mapPoints=[];imagePoints=[];projected=null;confirmed.checked=false;exported=false;draw();}
  function remember(){
    try{
      const all=saved();
      all[storageId()]={map_points:mapPoints,image_points:imagePoints,
        canvas:{width:Number(layout().canvas.width),height:Number(layout().canvas.height)},
        layout_signature:core.layoutSignature(layout()),
        image_ratio:image.naturalWidth/image.naturalHeight};
      localStorage.setItem(memoryKey,JSON.stringify(all));
    }catch{notify("端末への位置合わせ保存に失敗しました。JSONを書き出して保管してください。");}
  }
  function restore(){
    const item=saved()[storageId()],current=layout();
    const same=item&&current&&item.canvas?.width===Number(current.canvas.width)
      &&item.canvas?.height===Number(current.canvas.height);
    mapPoints=same&&Array.isArray(item.map_points)?item.map_points.slice(0,core.MAX_PAIRS):[];
    imagePoints=same&&Array.isArray(item.image_points)?item.image_points.slice(0,core.MAX_PAIRS):[];
    layoutChanged=Boolean(same&&item.layout_signature
      &&item.layout_signature!==core.layoutSignature(current));
    projected=null;confirmed.checked=false;exported=false;draw();
    if(mapPoints.length>=4&&mapPoints.length===imagePoints.length){
      notify(layoutChanged
        ? "駐車区画の配置が前回から変わりました。保存済み4点を再利用できますが、映像上ですべての区画位置を再確認してください。"
        : "前回の4点を読み込みました。最新のカメラ写真を読み込むと自動で区画を再計算します。");
    }
  }
  function loadPhoto(src){
    image.onload=()=>{
      image.hidden=false;projected=null;confirmed.checked=false;exported=false;
      const prior=saved()[storageId()];
      const ratio=image.naturalWidth/image.naturalHeight;
      if(prior?.image_ratio && Math.abs(ratio/prior.image_ratio-1)>.015){
        reset();
        notify("前回の画像と縦横比が異なります。画角を確認して対応点を登録し直してください。");
        return;
      }
      if(mapPoints.length>=4&&mapPoints.length===imagePoints.length){
        try{
          projected=generateVisibleZones();
          draw();
          notify(layoutChanged
            ? "マップ変更後の全区画を再計算しました。各点の誤差と映像上の位置を確認してください。"
            : "保存済み"+mapPoints.length+"点から再計算しました。必要なら追加点も指定できます。");
          return;
        }catch(error){projected=null;draw();notify("自動再計算できません: "+error.message);return;}
      }
      draw();
      notify("画像を読み込みました。マップと映像で対応する床面の点を交互に選んでください。");
    };
    image.onerror=()=>{image.hidden=true;reset();notify("画像を読み込めませんでした。別の写真を選んでください。");};
    image.src=src;
  }
  const launch=()=>{
    currentFacility=state.facilityId;
    const current=layout();
    if(!current)return;
    cameraId.value=currentFacility==="nikko-test-001"?"nikko-recording-01"
      : document.querySelector("#camera-monitor select")?.value||"home-camera-01";
    image.hidden=true;image.removeAttribute("src");file.value="";projected=null;confirmed.checked=false;
    showWholeMap=false;exported=false;
    dialog.showModal();restore();
    renderCoverageChoices();
    facilityLabel.textContent=document.querySelector("#facility-select")?.selectedOptions?.[0]?.textContent
      ||currentFacility;
    refresh();
    if(!(current.objects||[]).some(o=>o.objectType==="parkingSpace")){
      notify("先に管理マップで駐車区画を作成してください。");
    }
  };
  open.addEventListener("click",launch);
  document.addEventListener("parking:open-camera-alignment",launch);
  get("alignment-close").addEventListener("click",()=>dialog.close());
  dialog.addEventListener("close",()=>{
    if(fileUrl){URL.revokeObjectURL(fileUrl);fileUrl=null;}
    image.removeAttribute("src");image.hidden=true;
  });
  get("alignment-use-camera").addEventListener("click",()=>{
    const camera=document.querySelector("#camera-monitor img");
    if(camera?.hidden||!camera?.src){
      notify("『カメラを確認』で写真を取得するか、画像ファイルを選択してください。");return;
    }
    if(fileUrl){URL.revokeObjectURL(fileUrl);fileUrl=null;}
    loadPhoto(camera.src);
  });
  file.addEventListener("change",()=>{
    const chosen=file.files?.[0];
    if(!chosen)return;
    if(!["image/jpeg","image/png","image/webp"].includes(chosen.type)||chosen.size>12*1024*1024){
      image.hidden=true;
      image.removeAttribute("src");
      projected=null;confirmed.checked=false;exported=false;
      draw();
      notify("JPEG・PNG・WebPの12MB以下の画像を選んでください。");
      return;
    }
    if(fileUrl)URL.revokeObjectURL(fileUrl);
    fileUrl=URL.createObjectURL(chosen);
    loadPhoto(fileUrl);
  });
  map.addEventListener("click",event=>{
    if(mapPoints.length!==imagePoints.length||mapPoints.length>=core.MAX_PAIRS)return;
    try{mapPoints.push(pointFromClick(event,map));projected=null;confirmed.checked=false;exported=false;draw();}
    catch(error){notify(error.message);}
  });
  overlay.addEventListener("click",event=>{
    if(image.hidden||mapPoints.length!==imagePoints.length+1)return;
    try{imagePoints.push(pointFromClick(event,overlay));projected=null;confirmed.checked=false;exported=false;draw();}
    catch(error){notify(error.message);}
  });
  get("alignment-undo").addEventListener("click",()=>{
    if(mapPoints.length>imagePoints.length)mapPoints.pop();
    else if(imagePoints.length){mapPoints.pop();imagePoints.pop();}
    projected=null;confirmed.checked=false;exported=false;draw();
  });
  get("alignment-reset").addEventListener("click",reset);
  zoom.addEventListener("click",()=>{showWholeMap=!showWholeMap;draw();});
  cameraId.addEventListener("change",()=>{
    // カメラIDだけを変更して別カメラの写真を誤利用しない。
    image.hidden=true;
    image.removeAttribute("src");
    file.value="";exported=false;
    restore();
    notify("カメラを変更しました。対象カメラの写真を読み直して位置を確認してください。");
  });
  confirmed.addEventListener("change",refresh);
  applyButton.addEventListener("click",()=>{
    if(image.hidden||!image.naturalWidth){notify("先にカメラ画像を読み込んでください。");return;}
    try{
      projected=generateVisibleZones();
      confirmed.checked=false;exported=false;draw();
      notify(currentFacility==="nikko-test-001"
        ? "映像に完全に映る"+projected.space_uids.length+"区画を投影しました。画角外・極小の"+projected.excluded_space_uids.length+"区画は判定対象外です。全区画の位置を確認してください。"
        : "全区画を自動配置しました。画像上の緑色の枠を確認し、正しい場合だけJSONを書き出してください。");
    }catch(error){projected=null;draw();notify(error.message);}
  });
  exportButton.addEventListener("click",()=>{
    if(!projected||!layout()||image.hidden||!confirmed.checked||
        projected.alignmentDiagnostics?.outlierIndices?.length)return;
    const cam=cameraId.value.trim();
    if(!/^[A-Za-z0-9_-]{1,100}$/.test(cam)){
      notify("カメラIDは半角英数字・ハイフン・アンダースコアで入力してください。");return;
    }
    try{
      const result=generateVisibleZones();
      remember();layoutChanged=false;
      const info=result.alignmentDiagnostics;
      if(info.outlierIndices.length)throw Error("誤差の大きい点を削除・選び直してください。");
      const rmsPx=Math.sqrt(info.inlierIndices.reduce((sum,i)=>{
        const [dx,dy]=info.residualVectors[i];
        return sum+(dx*image.naturalWidth)**2+(dy*image.naturalHeight)**2;
      },0)/info.inlierIndices.length);
      const payload={
        schema_version:1,facility_id:currentFacility,camera_id:cam,
        alignment_quality:{method:info.method,point_count:info.pairCount,
          inlier_count:info.inlierIndices.length,outlier_indices:[],
          rms_pixels:Number(rmsPx.toFixed(3))},
        image_width:image.naturalWidth,image_height:image.naturalHeight,
        map_canvas:{width:layout().canvas.width,height:layout().canvas.height},
        map_points:mapPoints,image_points:imagePoints,
        space_uids:result.space_uids,space_zones:result.space_zones,
        excluded_space_uids:result.excluded_space_uids
      };
      const blob=new Blob([JSON.stringify(payload,null,2)+"\n"],{type:"application/json"});
      const url=URL.createObjectURL(blob),link=document.createElement("a");
      link.href=url;link.download="camera-map-alignment-"+currentFacility+"-"+cam+".json";
      link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
      exported=true;refresh();
      notify(currentFacility==="nikko-test-001"
        ? "日光録画の位置合わせJSONを保存しました。PCで元動画に重ねて確認してから取り込んでください。"
        : "位置合わせJSONを保存しました。次はPCで実カメラ映像と区画の一致を確認してください。");
    }catch(error){notify(error.message);}
  });
})();
