/* カメラ画像と管理マップの4～24点対応から、全駐車区画を投影する純粋関数。
 * 映像・クラウド・既存レイアウトの状態は変更しない。
 * カメラと駐車場の床面が1つの平面であることを前提とする。
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.ParkingCameraMapAlignment = api;
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  function point(value) {
    if (!Array.isArray(value) || value.length !== 2 ||
        !value.every(v => typeof v === "number" && Number.isFinite(v))) {
      throw new Error("対応点は有限な数値2個で指定してください。");
    }
    return value;
  }

  function hullArea(input) {
    const sorted = input.map(point).map(p => p.slice()).sort((a,b) => a[0]-b[0] || a[1]-b[1]);
    const cross = (a,b,c) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
    const lower=[], upper=[];
    for(const p of sorted){while(lower.length>1 && cross(lower.at(-2),lower.at(-1),p)<=0)lower.pop();lower.push(p);}
    for(const p of sorted.slice().reverse()){while(upper.length>1 && cross(upper.at(-2),upper.at(-1),p)<=0)upper.pop();upper.push(p);}
    const hull=lower.slice(0,-1).concat(upper.slice(0,-1));
    return Math.abs(hull.reduce((sum,p,i)=>sum+p[0]*hull[(i+1)%hull.length][1]-p[1]*hull[(i+1)%hull.length][0],0))/2;
  }

  function solve(equations, values) {
    const a=equations.map((row,i)=>[...row,values[i]]);
    for(let k=0;k<8;k++){
      let pivot=k;
      for(let i=k+1;i<8;i++)if(Math.abs(a[i][k])>Math.abs(a[pivot][k]))pivot=i;
      if(Math.abs(a[pivot][k])<1e-10)throw new Error("対応点が近すぎるか一直線です。離れた4点を選び直してください。");
      [a[k],a[pivot]]=[a[pivot],a[k]];
      const div=a[k][k];
      for(let j=k;j<=8;j++)a[k][j]/=div;
      for(let i=0;i<8;i++)if(i!==k){
        const factor=a[i][k];
        for(let j=k;j<=8;j++)a[i][j]-=factor*a[k][j];
      }
    }
    return a.map(row=>row[8]);
  }

  const MAX_PAIRS=24;
  // 誤差が画像幅/高さの約1%を超える対応点は外れ点の候補とする。
  // 4点の厳密投影は従来互換、5点以上は外れ点を除いた最小二乗推定。
  const INLIER_THRESHOLD=.012;

  function validatePairs(mapPoints,imagePoints){
    const n=mapPoints?.length;
    if(!Array.isArray(mapPoints)||!Array.isArray(imagePoints)||
       n!==imagePoints.length||n<4||n>MAX_PAIRS){
      throw new Error("マップと映像で同じ場所を4～24組指定してください。");
    }
    for(const p of [...mapPoints,...imagePoints]){
      point(p);
      if(p.some(v=>v<0||v>1))throw new Error("対応点が画像またはマップの範囲外です。");
    }
    if(hullArea(mapPoints)<.005||hullArea(imagePoints)<.005){
      throw new Error("対応点が狭い範囲に集中しています。駐車場全体に広く配置してください。");
    }
    return n;
  }

  /** 正規化したx,y->u,vの8係数を、4点は厳密に、5点以上は最小二乗で解く。 */
  function solveFromPairs(mapPoints,imagePoints,indices){
    const equations=[],values=[];
    for(const i of indices){
      const [x,y]=mapPoints[i],[u,v]=imagePoints[i];
      equations.push([x,y,1,0,0,0,-x*u,-y*u]);
      values.push(u);
      equations.push([0,0,0,x,y,1,-x*v,-y*v]);
      values.push(v);
    }
    if(indices.length===4)return solve(equations,values);
    const normal=Array.from({length:8},()=>Array(8).fill(0));
    const right=Array(8).fill(0);
    for(let r=0;r<equations.length;r++){
      const row=equations[r];
      for(let i=0;i<8;i++){
        right[i]+=row[i]*values[r];
        for(let j=0;j<8;j++)normal[i][j]+=row[i]*row[j];
      }
    }
    return solve(normal,right);
  }

  function pairResiduals(matrix,mapPoints,imagePoints){
    return mapPoints.map((p,i)=>{
      try{
        const transformed=project(matrix,p);
        return [transformed[0]-imagePoints[i][0],transformed[1]-imagePoints[i][1]];
      }catch{return [Infinity,Infinity];}
    });
  }

  function inliersFor(residualVectors,threshold){
    return residualVectors.flatMap(([dx,dy],i)=>
      Math.hypot(dx,dy)<=threshold?[i]:[]);
  }

  /** 4点の厳密法と、多点RANSAC+最小二乗法を統一して診断も返す。 */
  function fitHomography(mapPoints,imagePoints){
    const n=validatePairs(mapPoints,imagePoints);
    const all=Array.from({length:n},(_,i)=>i);
    let matrix,indices=all;
    if(n===4){
      matrix=solveFromPairs(mapPoints,imagePoints,all);
    }else{
      // 再現性のある4点組合せを最大約500組評価。乱数に依存しない。
      const combinations=n*(n-1)*(n-2)*(n-3)/24;
      const stride=Math.max(1,Math.floor(combinations/480));
      let count=0,best=null;
      for(let a=0;a<n-3;a++)for(let b=a+1;b<n-2;b++)
        for(let c=b+1;c<n-1;c++)for(let d=c+1;d<n;d++){
          if(count++%stride!==0)continue;
          const sample=[a,b,c,d];
          if(hullArea(sample.map(i=>mapPoints[i]))<.005 ||
             hullArea(sample.map(i=>imagePoints[i]))<.005)continue;
          let trial;
          try{trial=solveFromPairs(mapPoints,imagePoints,sample);}
          catch{continue;}
          const residuals=pairResiduals(trial,mapPoints,imagePoints);
          const fit=inliersFor(residuals,INLIER_THRESHOLD);
          if(fit.length<4)continue;
          const sum=fit.reduce((total,i)=>total+
            residuals[i][0]**2+residuals[i][1]**2,0);
          if(!best||fit.length>best.indices.length||
             (fit.length===best.indices.length&&sum<best.sum)){
            best={indices:fit,sum};
          }
        }
      if(!best)throw new Error("対応点に整合性がありません。地面上の同じ場所を選び直してください。");
      indices=best.indices;
      for(let iteration=0;iteration<3;iteration++){
        matrix=solveFromPairs(mapPoints,imagePoints,indices);
        const newIndices=inliersFor(pairResiduals(matrix,mapPoints,imagePoints),INLIER_THRESHOLD);
        if(newIndices.length<4)throw new Error("一致する対応点が4組未満です。点を確認してください。");
        if(newIndices.join(",")===indices.join(","))break;
        indices=newIndices;
      }
      // 最後に採用された全点で解き直す（5点以上では最小二乗）。
      matrix=solveFromPairs(mapPoints,imagePoints,indices);
    }
    const residualVectors=pairResiduals(matrix,mapPoints,imagePoints);
    const finalInliers=inliersFor(residualVectors,INLIER_THRESHOLD);
    const outlierIndices=all.filter(i=>!finalInliers.includes(i));
    const accepted=finalInliers.length>=4?finalInliers:indices;
    const rmsNormalized=Math.sqrt(accepted.reduce((total,i)=>
      total+residualVectors[i][0]**2+residualVectors[i][1]**2,0)/accepted.length);
    return {matrix,residualVectors,inlierIndices:accepted,outlierIndices,
      rmsNormalized,method:n===4?"four-point":"ransac-least-squares",
      pairCount:n,threshold:INLIER_THRESHOLD};
  }

  /** 旧来のhomography APIは配列（8係数）を返す。 */
  function homography(mapPoints,imagePoints){
    return fitHomography(mapPoints,imagePoints).matrix;
  }

  function project(matrix, coord) {
    const [x,y]=point(coord);
    const denominator=matrix[6]*x+matrix[7]*y+1;
    if(Math.abs(denominator)<1e-8)throw new Error("投影できない座標が含まれます。対応点を確認してください。");
    const u=(matrix[0]*x+matrix[1]*y+matrix[2])/denominator;
    const v=(matrix[3]*x+matrix[4]*y+matrix[5])/denominator;
    if(!Number.isFinite(u)||!Number.isFinite(v))throw new Error("位置合わせの計算結果が不正です。");
    return [u,v];
  }

  /** 管理者アプリのCSS回転は長方形の中心を基準にする。 */
  function parkingCorners(item) {
    if(item?.objectType!=="parkingSpace")throw new Error("駐車区画以外は投影できません。");
    const x=Number(item.x),y=Number(item.y),w=Number(item.width),h=Number(item.height);
    const deg=Number(item.rotation||0);
    if(![x,y,w,h,deg].every(Number.isFinite)||w<=0||h<=0){
      throw new Error("区画の位置・寸法・回転角度が不正です。");
    }
    const cx=x+w/2,cy=y+h/2,ang=deg*Math.PI/180,c=Math.cos(ang),s=Math.sin(ang);
    return [[x,y],[x+w,y],[x+w,y+h],[x,y+h]].map(([px,py])=>{
      const dx=px-cx,dy=py-cy;
      return [cx+dx*c-dy*s,cy+dx*s+dy*c];
    });
  }

  function signedArea(points){
    return points.reduce((sum,p,i)=>sum+p[0]*points[(i+1)%points.length][1]-p[1]*points[(i+1)%points.length][0],0)/2;
  }

  /** 各区画の四隅が映像内にある場合だけ、monitor.py と互換の0～1座標を生成。 */
  function generateZones(layout,mapPoints,imagePoints, options={}) {
    const width=Number(layout?.canvas?.width),height=Number(layout?.canvas?.height);
    if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0)throw new Error("マップの大きさが不正です。");
    const alignmentDiagnostics=fitHomography(mapPoints,imagePoints);
    const transform=alignmentDiagnostics.matrix;
    const slots=(layout?.objects||[]).filter(o=>o?.objectType==="parkingSpace");
    if(slots.length===0)throw new Error("このマップには駐車区画がありません。");
    const zones={},excluded=[];const seen=new Set();
    const skipOutside=options.skipOutsideFrame===true;
    for(const slot of slots){
      const uid=String(slot.uid||"");
      if(!/^space_[A-Za-z0-9_-]+$/.test(uid)||seen.has(uid)){
        throw new Error("区画IDが不正または重複しています: "+uid);
      }
      seen.add(uid);
      // 道の駅日光の管理マップには映像外の駐車枠も残す。
      // 明示的に「画角外」とした区画は、計算上は写真内でもYOLOには渡さない。
      if(skipOutside && slot.cameraCoverage==="outside"){
        excluded.push(uid);
        continue;
      }
      let result;
      try{result=parkingCorners(slot).map(([x,y])=>project(transform,[x/width,y/height]));}
      catch(error){if(skipOutside){excluded.push(uid);continue;}throw error;}
      if(result.some(p=>p.some(n=>n < -1e-7 || n > 1+1e-7))){
        if(skipOutside){excluded.push(uid);continue;}
        throw new Error(uid+" が撮影範囲外です。カメラを追加するか対応点を見直してください。");
      }
      if(Math.abs(signedArea(result))<0.00001 || hullArea(result)<0.00001){
        if(skipOutside){excluded.push(uid);continue;}
        throw new Error(uid+" が極端に小さく映ります。カメラの位置を変更してください。");
      }
      // 4頂点が適切な周回順になるかを保証。視点が床面の裏側に回る変換も拒否。
      if(Math.abs(Math.abs(signedArea(result))-hullArea(result))>1e-6){
        throw new Error(uid+" の四隅が交差しています。対応点を選び直してください。");
      }
      zones[uid]=result.map(p=>p.map(n=>Number(Math.max(0,Math.min(1,n)).toFixed(7))));
    }
    if(!Object.keys(zones).length)throw new Error("カメラ映像に完全に入る駐車区画がありません。画角と対応点を確認してください。");
    return {space_uids:Object.keys(zones),space_zones:zones,excluded_space_uids:excluded,
      transform,alignmentDiagnostics};
  }

  /** 写真を直接なぞった4頂点。実行側のzone_geometry.normalize_cornersと同じ安全条件。 */
  function normalizeCameraZone(corners){
    if(!Array.isArray(corners)||corners.length!==4)
      throw new Error("駐車枠の角を写真上で4か所指定してください。");
    const coords=corners.map(p=>{
      point(p);
      if(p.some(n=>n<0||n>1))throw new Error("駐車枠は写真の内側に指定してください。");
      return p.slice();
    });
    const cx=coords.reduce((a,p)=>a+p[0]/4,0);
    const cy=coords.reduce((a,p)=>a+p[1]/4,0);
    const ordered=coords.slice().sort((a,b)=>
      Math.atan2(a[1]-cy,a[0]-cx)-Math.atan2(b[1]-cy,b[0]-cx));
    if(new Set(ordered.map(p=>p.map(x=>x.toFixed(5)).join(":"))).size!==4)
      throw new Error("同じ角を複数回選んでいます。別の四隅を指定してください。");
    if(Math.abs(signedArea(ordered))<.00005)
      throw new Error("枠が小さすぎるか、四隅がほぼ一直線です。");
    const signs=[];
    for(let i=0;i<4;i++){
      const a=ordered[i],b=ordered[(i+1)%4],c=ordered[(i+2)%4];
      const z=(b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0]);
      if(Math.abs(z)<.0000005)
        throw new Error("四隅の形が崩れています。区画の白線に沿って選び直してください。");
      signs.push(z>0);
    }
    if(!signs.every(v=>v===signs[0]))
      throw new Error("四隅が凸四角形になりません。枠線に沿って指定してください。");
    return ordered.map(p=>p.map(n=>Number(n.toFixed(5))));
  }

  /** 管理マップのUIDを保存し、カメラ側の個別枠だけ上書きする。
   * automatic=nullなら写真だけの直接登録。指定しない区画はすべて画角外。
   * カメラ範囲外を明示した枠は、写真の手動登録でも空き判定の対象にしない。
   */
  function composeCameraZones(layout,automatic,manualZones={}){
    const slots=(layout?.objects||[]).filter(o=>o?.objectType==="parkingSpace");
    if(!slots.length)throw new Error("管理マップに駐車枠がありません。");
    if(!manualZones||typeof manualZones!=="object"||Array.isArray(manualZones))
      throw new Error("写真の駐車枠設定が不正です。");
    const ids=new Set(slots.map(slot=>String(slot.uid)));
    if(ids.size!==slots.length)throw new Error("区画IDが重複しています。");
    const valid=(uid)=>/^space_[A-Za-z0-9_-]+$/.test(uid);
    const src=automatic?.space_zones||{};
    for(const uid of Object.keys(src))if(!ids.has(uid)||!valid(uid))
      throw new Error("管理マップに存在しない区画の自動投影です: "+uid);
    for(const uid of Object.keys(manualZones))if(!ids.has(uid)||!valid(uid))
      throw new Error("管理マップに存在しない区画の手動設定です: "+uid);
    const zones={},excluded=[];
    for(const slot of slots){
      const uid=String(slot.uid);
      if(!valid(uid))throw new Error("区画IDが不正です: "+uid);
      if(slot.cameraCoverage==="outside"){
        excluded.push(uid);continue;
      }
      const raw=Object.hasOwn(manualZones,uid)?manualZones[uid]:src[uid];
      if(raw===undefined){excluded.push(uid);continue;}
      zones[uid]=Object.hasOwn(manualZones,uid)
        ? normalizeCameraZone(raw)
        : raw.map(p=>p.slice());
    }
    if(!Object.keys(zones).length)
      throw new Error("写真上に登録された駐車枠がありません。区画を1つ以上登録してください。");
    return {space_uids:Object.keys(zones),space_zones:zones,excluded_space_uids:excluded,
      transform:automatic?.transform??null,
      alignmentDiagnostics:automatic?.alignmentDiagnostics??null,
      alignmentMethod:automatic?"hybrid-zones":"manual-zones",
      manual_zone_uids:Object.keys(manualZones).filter(uid=>Object.hasOwn(zones,uid))};
  }

  /** 位置合わせ後に区画が編集されたかを判断するための安定した配置署名。 */
  function layoutSignature(layout){
    const slots=(layout?.objects||[]).filter(item=>item?.objectType==="parkingSpace")
      .map(item=>[String(item.uid),Number(item.x),Number(item.y),Number(item.width),
                  Number(item.height),Number(item.rotation||0),String(item.cameraCoverage||"auto")])
      .sort((a,b)=>a[0].localeCompare(b[0],"en"));
    return JSON.stringify({
      canvas:[Number(layout?.canvas?.width),Number(layout?.canvas?.height)],
      slots
    });
  }

  /** 大きな管理マップでも区画が読めるように、全区画へ視界を寄せる。
   * 対応座標は表示倍率に左右されず常に管理マップ全体の座標で扱う。
   */
  function parkingViewport(layout, marginRatio=0.18) {
    const width=Number(layout?.canvas?.width),height=Number(layout?.canvas?.height);
    if(!Number.isFinite(width)||!Number.isFinite(height)||width<=0||height<=0) {
      throw new Error("マップの大きさが不正です。");
    }
    const whole={x:0,y:0,width,height};
    const slots=(layout?.objects||[]).filter(item=>item?.objectType==="parkingSpace");
    if(!slots.length)return whole;
    let points;
    try {points=slots.flatMap(parkingCorners);}
    catch {return whole;} // 不正な区画は自動計算時に警告し、画面全体は表示し続ける。
    if(!points.every(([x,y])=>Number.isFinite(x)&&Number.isFinite(y)))return whole;
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const padX=Math.max(width*.016,(maxX-minX)*Math.max(0,marginRatio));
    const padY=Math.max(height*.016,(maxY-minY)*Math.max(0,marginRatio));
    const x=Math.max(0,minX-padX),y=Math.max(0,minY-padY);
    const right=Math.min(width,maxX+padX),bottom=Math.min(height,maxY+padY);
    const result={x,y,width:Math.max(1,right-x),height:Math.max(1,bottom-y)};
    if(result.width>=width*.96&&result.height>=height*.96)return whole;
    return result;
  }

  return Object.freeze({homography,fitHomography,project,parkingCorners,generateZones,normalizeCameraZone,composeCameraZones,hullArea,layoutSignature,parkingViewport,MAX_PAIRS});
});
