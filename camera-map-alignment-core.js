/* カメラ画像と管理マップの4点対応から、全駐車区画を投影する純粋関数。
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

  /** mapPoints/imagePoints は、それぞれ0～1に正規化した対応座標。 */
  function homography(mapPoints,imagePoints){
    if(mapPoints?.length!==4 || imagePoints?.length!==4)throw new Error("マップと映像の対応点を4組指定してください。");
    for(const p of [...mapPoints,...imagePoints]){
      point(p);
      if(p.some(v=>v<0||v>1))throw new Error("対応点が画像またはマップの範囲外です。");
    }
    if(hullArea(mapPoints)<0.005 || hullArea(imagePoints)<0.005){
      throw new Error("4点が狭い範囲に集中しています。駐車場の広い範囲で4点を選んでください。");
    }
    const equations=[],values=[];
    for(let i=0;i<4;i++){
      const [x,y]=mapPoints[i],[u,v]=imagePoints[i];
      equations.push([x,y,1,0,0,0,-x*u,-y*u]);
      values.push(u);
      equations.push([0,0,0,x,y,1,-x*v,-y*v]);
      values.push(v);
    }
    return solve(equations,values);
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
    const transform=homography(mapPoints,imagePoints);
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
    if(!Object.keys(zones).length)throw new Error("カメラ映像に完全に入る駐車区画がありません。画角と4点を確認してください。");
    return {space_uids:Object.keys(zones),space_zones:zones,excluded_space_uids:excluded,transform};
  }

  /** 位置合わせ後に区画が編集されたかを判断するための安定した配置署名。 */
  function layoutSignature(layout){
    const slots=(layout?.objects||[]).filter(item=>item?.objectType==="parkingSpace")
      .map(item=>[String(item.uid),Number(item.x),Number(item.y),Number(item.width),
                  Number(item.height),Number(item.rotation||0)])
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

  return Object.freeze({homography,project,parkingCorners,generateZones,hullArea,layoutSignature,parkingViewport});
});
