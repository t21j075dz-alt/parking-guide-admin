"use strict";
/* 両アプリで同じ番号・文字寸法・標識／路面標示を使う。保存データは書き換えない。 */
window.ParkingMapDisplay = (() => {
  const types = ["parkingLot","excludedParkingLot","nationalRoad","prefecturalRoad","publicRoad","parkingSpace","road","sidewalk","crosswalk","building","buildingEntrance","parkingEntrance","stopLine","speedBump","noEntry","cartCorral","bicycleParking","motorcycleParking","loadingZone","evCharger","roadSign","pavementMarking"];
  // 全国共通の全分類ではなく、資料確認済みの用途と編集用プリセット。寸法根拠は各項目で区別する。
  const spacePresets = Object.freeze(Object.fromEntries(Object.entries({
  "standard": {
    "label": "普通車",
    "en": "Standard car",
    "mark": "",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "乗用車",
    "basis": "既存アプリ初期値",
    "guidable": true
  },
  "compact": {
    "label": "軽自動車",
    "en": "Kei car",
    "mark": "軽",
    "widthMeters": 2,
    "lengthMeters": 3.6,
    "group": "乗用車",
    "basis": "国交省指針",
    "guidable": true
  },
  "smallCar": {
    "label": "小型乗用車",
    "en": "Small passenger car",
    "mark": "小型",
    "widthMeters": 2.3,
    "lengthMeters": 5,
    "group": "乗用車",
    "basis": "国交省指針",
    "guidable": true
  },
  "passengerLong": {
    "label": "普通乗用車・長さ6m",
    "en": "Passenger car (6 m bay)",
    "mark": "普通",
    "widthMeters": 2.5,
    "lengthMeters": 6,
    "group": "乗用車",
    "basis": "国交省指針",
    "guidable": true
  },
  "large": {
    "label": "大型車用",
    "en": "Large vehicle",
    "mark": "大型",
    "widthMeters": 3.3,
    "lengthMeters": 13,
    "group": "大型車・貨物車",
    "basis": "国交省指針",
    "guidable": true
  },
  "smallTruck": {
    "label": "小型貨物車用",
    "en": "Small truck",
    "mark": "小型\n貨物",
    "widthMeters": 3,
    "lengthMeters": 7.7,
    "group": "大型車・貨物車",
    "basis": "国交省指針",
    "guidable": true
  },
  "mediumTruck": {
    "label": "中型貨物車用",
    "en": "Medium truck",
    "mark": "中型\n貨物",
    "widthMeters": 3.3,
    "lengthMeters": 10,
    "group": "大型車・貨物車",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "largeTruck": {
    "label": "大型貨物車専用",
    "en": "Heavy truck only",
    "mark": "大型\n貨物",
    "widthMeters": 3.3,
    "lengthMeters": 13,
    "group": "大型車・貨物車",
    "basis": "国交省指針",
    "guidable": true
  },
  "trailer": {
    "label": "トレーラー専用",
    "en": "Trailer only",
    "mark": "トレーラー",
    "widthMeters": 3.5,
    "lengthMeters": 18,
    "group": "大型車・貨物車",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "doubleTrailer": {
    "label": "ダブル連結トラック専用・優先",
    "en": "Double-trailer truck",
    "mark": "ダブル\n連結",
    "widthMeters": 3.5,
    "lengthMeters": 27,
    "group": "大型車・貨物車",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "combined": {
    "label": "普通車・大型車兼用",
    "en": "Shared car / large vehicle bay",
    "mark": "兼用",
    "widthMeters": 3.3,
    "lengthMeters": 13,
    "group": "大型車・貨物車",
    "basis": "大型車指針を初期値に採用",
    "guidable": true,
    "markingStyle": "dashed",
    "markingColor": "#4ca3ff"
  },
  "bus": {
    "label": "バス専用",
    "en": "Bus only",
    "mark": "バス\n専用",
    "widthMeters": 3.3,
    "lengthMeters": 13,
    "group": "バス",
    "basis": "国交省指針",
    "guidable": true
  },
  "busPriority": {
    "label": "バス優先",
    "en": "Bus priority",
    "mark": "バス\n優先",
    "widthMeters": 3.3,
    "lengthMeters": 13,
    "group": "バス",
    "basis": "国交省指針",
    "guidable": true
  },
  "minibus": {
    "label": "マイクロバス専用",
    "en": "Minibus only",
    "mark": "マイクロ\nバス",
    "widthMeters": 3,
    "lengthMeters": 7.7,
    "group": "バス",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "rv": {
    "label": "キャンピングカー・RV",
    "en": "Camper / RV",
    "mark": "RV",
    "widthMeters": 4,
    "lengthMeters": 7,
    "group": "乗用車",
    "basis": "日本RV協会の推奨寸法",
    "guidable": true
  },
  "motorcycle": {
    "label": "自動二輪車用",
    "en": "Motorcycle",
    "mark": "二輪",
    "widthMeters": 1,
    "lengthMeters": 2.3,
    "group": "二輪・自転車",
    "basis": "福岡市の基準を参考",
    "guidable": true
  },
  "moped": {
    "label": "原付用",
    "en": "Moped",
    "mark": "原付",
    "widthMeters": 0.8,
    "lengthMeters": 2,
    "group": "二輪・自転車",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "bicycle": {
    "label": "自転車用",
    "en": "Bicycle",
    "mark": "自転車",
    "widthMeters": 0.6,
    "lengthMeters": 1.9,
    "group": "二輪・自転車",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "scooter": {
    "label": "特定小型原付・シェアモビリティ",
    "en": "Small mobility / scooter",
    "mark": "小型\nモビリティ",
    "widthMeters": 0.8,
    "lengthMeters": 2,
    "group": "二輪・自転車",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "accessible": {
    "label": "車いす使用者用",
    "en": "Wheelchair accessible",
    "mark": "車いす",
    "widthMeters": 3.5,
    "lengthMeters": 6,
    "group": "優先・配慮",
    "basis": "国交省幅・福岡市推奨長さ",
    "guidable": true
  },
  "priority": {
    "label": "優先・思いやり・パーキングパーミット",
    "en": "Priority / parking permit",
    "mark": "優先",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "優先・配慮",
    "basis": "既存アプリ初期値・現地条件",
    "guidable": true
  },
  "maternity": {
    "label": "妊産婦優先",
    "en": "Maternity priority",
    "mark": "妊産婦",
    "widthMeters": 3.5,
    "lengthMeters": 5,
    "group": "優先・配慮",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "senior": {
    "label": "高齢者優先",
    "en": "Senior priority",
    "mark": "高齢者",
    "widthMeters": 3.5,
    "lengthMeters": 5,
    "group": "優先・配慮",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "family": {
    "label": "子育て・ベビーカー優先",
    "en": "Family / stroller priority",
    "mark": "子育て",
    "widthMeters": 3.5,
    "lengthMeters": 5,
    "group": "優先・配慮",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "ev": {
    "label": "EV・PHEV充電用",
    "en": "EV / PHEV charging",
    "mark": "EV",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "充電",
    "basis": "既存アプリ初期値",
    "guidable": true
  },
  "evFast": {
    "label": "EV急速充電専用",
    "en": "EV rapid charging",
    "mark": "EV\n急速",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "充電",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "evAccessible": {
    "label": "車いす対応EV充電用",
    "en": "Accessible EV charging",
    "mark": "EV\n車いす",
    "widthMeters": 3.5,
    "lengthMeters": 6,
    "group": "充電",
    "basis": "車いす用初期値を採用",
    "guidable": true
  },
  "taxi": {
    "label": "タクシー専用駐車",
    "en": "Taxi parking",
    "mark": "タクシー",
    "widthMeters": 2.5,
    "lengthMeters": 6,
    "group": "専用・契約",
    "basis": "普通乗用車指針を初期値に採用",
    "guidable": true
  },
  "reserved": {
    "label": "予約専用",
    "en": "Reserved",
    "mark": "予約",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "monthly": {
    "label": "月極・契約者専用",
    "en": "Monthly / permit holder",
    "mark": "契約者",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "visitor": {
    "label": "来客・来庁者用",
    "en": "Visitor",
    "mark": "来客",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "customer": {
    "label": "店舗利用者専用",
    "en": "Customer only",
    "mark": "お客様",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "employee": {
    "label": "従業員・職員専用",
    "en": "Staff only",
    "mark": "職員",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "company": {
    "label": "社用車・公用車専用",
    "en": "Company / official vehicle",
    "mark": "公用車",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "carShare": {
    "label": "カーシェア専用",
    "en": "Car sharing only",
    "mark": "カー\nシェア",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "rental": {
    "label": "レンタカー専用",
    "en": "Rental car only",
    "mark": "レンタカー",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "hotel": {
    "label": "宿泊者専用",
    "en": "Hotel guest only",
    "mark": "宿泊者",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "shortStay": {
    "label": "短時間専用",
    "en": "Short stay only",
    "mark": "短時間",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "専用・契約",
    "basis": "編集用仮寸法・現地確認",
    "guidable": true
  },
  "loading": {
    "label": "荷さばき専用駐車",
    "en": "Loading / unloading parking",
    "mark": "荷さばき",
    "widthMeters": 3,
    "lengthMeters": 7.7,
    "group": "荷さばき",
    "basis": "福岡市基準・小型貨物車指針",
    "guidable": true
  },
  "delivery": {
    "label": "集配・配送車専用",
    "en": "Delivery vehicle",
    "mark": "集配",
    "widthMeters": 3,
    "lengthMeters": 7.7,
    "group": "荷さばき",
    "basis": "小型貨物車指針を初期値に採用",
    "guidable": true
  },
  "taxiStand": {
    "label": "タクシー乗降・待機",
    "en": "Taxi boarding / queue",
    "mark": "タクシー\n乗降",
    "widthMeters": 2.5,
    "lengthMeters": 6,
    "group": "乗降・管理専用（案内対象外）",
    "basis": "編集用仮寸法・現地確認",
    "guidable": false
  },
  "pickup": {
    "label": "送迎・乗降専用",
    "en": "Pick-up / drop-off",
    "mark": "送迎\n乗降",
    "widthMeters": 2.5,
    "lengthMeters": 6,
    "group": "乗降・管理専用（案内対象外）",
    "basis": "編集用仮寸法・現地確認",
    "guidable": false
  },
  "busBoarding": {
    "label": "バス乗降・乗り場",
    "en": "Bus boarding",
    "mark": "バス\n乗降",
    "widthMeters": 3.3,
    "lengthMeters": 13,
    "group": "乗降・管理専用（案内対象外）",
    "basis": "大型車指針を初期値に採用",
    "guidable": false
  },
  "emergency": {
    "label": "緊急車両専用",
    "en": "Emergency vehicle only",
    "mark": "緊急車",
    "widthMeters": 3.3,
    "lengthMeters": 13,
    "group": "乗降・管理専用（案内対象外）",
    "basis": "編集用仮寸法・現地確認",
    "guidable": false
  },
  "fireAccess": {
    "label": "消防活動用空地・駐車禁止",
    "en": "Fire access / no parking",
    "mark": "消防活動\n駐車禁止",
    "widthMeters": 6,
    "lengthMeters": 12,
    "group": "乗降・管理専用（案内対象外）",
    "basis": "魚沼市の例・地域基準を確認",
    "guidable": false,
    "markingStyle": "hatched",
    "markingColor": "#facc15"
  },
  "custom": {
    "label": "カスタム・施設独自区画",
    "en": "Custom / site-specific",
    "mark": "専用",
    "widthMeters": 2.5,
    "lengthMeters": 5,
    "group": "カスタム（案内対象外）",
    "basis": "名称・寸法を現地に合わせて編集",
    "guidable": false
  }
}).map(([key,value])=>[key,Object.freeze(value)])));
  function spaceTypeLabel(type,english=false){const p=spacePresets[type];return p?(english?p.en:p.label):String(type||"普通車");}
  function isGuidableType(type){return spacePresets[type]?.guidable===true;}
  const roads = new Set(["road","nationalRoad","prefecturalRoad","publicRoad"]);
  function normalizeNumber(value) {
    return String(value ?? "").normalize("NFKC").trim().replace(/\d+/g, n => n.replace(/^0+(?=\d)/,""));
  }
  function spaceNumber(item) {
    return normalizeNumber(item?.spaceNumber ?? String(item?.name ?? "").match(/(?:普通車|軽|車椅子|EV|駐車区画)\s+(\d+)$/)?.[1] ?? item?.name ?? "");
  }
  function groupName(item) {
    const name = String(item?.spaceGroup ?? "").normalize("NFKC").trim().replace(/(?:区画|列)$/u, "");
    return name ? name + (item.spaceGroupKind === "area" ? "区画" : "列") : "";
  }
  function spaceName(item) { return [groupName(item),spaceNumber(item)].filter(Boolean).join(" "); }
  function units(text) { return [...String(text)].reduce((n,c) => n + (/^[\x00-\x7f]$/.test(c) ? .62 : 1),0); }
  function fitLabel(text,width,height,max=14) {
    const lines = String(text).split("\n");
    const w = Math.max(.1,Number(width)||.1), h = Math.max(.1,Number(height)||.1);
    return Math.max(.001,Math.min(max,w*.86/Math.max(1,...lines.map(units)),h*.78/(lines.length*1.2)));
  }
  function groupKey(item) { return groupName(item); }
  function numberConflict(item,layout,number,group,kind) {
    const key = groupName({spaceGroup:group,spaceGroupKind:kind});
    return (layout?.objects??[]).some(other=>other.objectType === "parkingSpace" && other.uid !== item.uid
      && groupKey(other) === key && spaceNumber(other) === normalizeNumber(number));
  }
  function svgElement(tag,attrs={},text) {
    const el=document.createElementNS("http://www.w3.org/2000/svg",tag);
    Object.entries(attrs).forEach(([key,value])=>el.setAttribute(key,String(value)));
    if(text != null)el.textContent=text;
    return el;
  }
  function svgRoot(width,height,className) {
    return svgElement("svg",{viewBox:`0 0 ${width} ${height}`,preserveAspectRatio:"xMidYMid meet",class:className,"aria-hidden":"true"});
  }
  function face(item) {
    const svg=svgRoot(100,120,"shared-sign-graphic");
    const sign=item.signType??"nationalRoute";
    svg.append(svgElement("rect",{x:47,y:77,width:6,height:42,fill:"#6b7280"}));
    if(sign === "noEntry") {
      svg.append(svgElement("circle",{cx:50,cy:42,r:40,fill:"#c81e1e",stroke:"white","stroke-width":3}));
      svg.append(svgElement("rect",{x:17,y:34,width:66,height:16,fill:"white",rx:2}));
    } else if(sign === "stop") {
      svg.append(svgElement("polygon",{points:"3,3 97,3 50,85",fill:"#c81e1e",stroke:"white","stroke-width":3,"stroke-linejoin":"round"}));
      svg.append(svgElement("text",{x:50,y:29,"text-anchor":"middle",fill:"white","font-size":20,"font-weight":700},"止まれ"));
      svg.append(svgElement("text",{x:50,y:46,"text-anchor":"middle",fill:"white","font-size":11,"font-weight":700},"STOP"));
    } else {
      const shape=sign === "prefecturalRoute" ? "50,2 94,23 83,69 50,84 17,69 6,23" : "10,3 90,3 96,14 82,65 50,84 18,65 4,14";
      svg.append(svgElement("polygon",{points:shape,fill:"#1256a0",stroke:"white","stroke-width":3,"stroke-linejoin":"round"}));
      const heading=sign === "prefecturalRoute" ? item.prefectureName||"県道" : "国道";
      const number=normalizeNumber(item.routeNumber)||"?";
      svg.append(svgElement("text",{x:50,y:24,"text-anchor":"middle",fill:"white","font-size":fitLabel(heading,72,20,14),"font-weight":700},heading));
      svg.append(svgElement("text",{x:50,y:58,"text-anchor":"middle",fill:"white","font-size":fitLabel(number,70,39,32),"font-weight":800},number));
    }
    return svg;
  }
  function appendSign(node,item) { node.dataset.signType=item.signType??"nationalRoute"; node.append(face(item)); }
  function appendRoute(node,item,layout) {
    if(!["nationalRoad","prefecturalRoad"].includes(item.objectType) || !String(item.routeNumber??"").trim())return;
    if((layout?.objects??[]).some(o=>o.objectType==="roadSign" && o.linkedRoadUid===item.uid && ["nationalRoute","prefecturalRoute"].includes(o.signType) && normalizeNumber(o.routeNumber)===normalizeNumber(item.routeNumber)))return;
    const wrapper=document.createElement("div"); wrapper.className="shared-route-shield";
    const size=Math.max(.5,Math.min(Number(item.width)||1,Number(item.height)||1)*.82);
    wrapper.style.width=`${size}px`;wrapper.style.height=`${size}px`;
    // 利用者マップはscreenScale分の寸法を明示し、編集キャンバスは親の倍率に追従。
    const scale=Number(node.dataset.screenScale)||1;
    wrapper.style.width=`${size*scale}px`;wrapper.style.height=`${size*scale}px`;
    wrapper.style.transform=`translate(-50%,-50%) rotate(${-(Number(item.rotation)||0)}deg)`;
    wrapper.append(face({...item,signType:item.objectType==="nationalRoad"?"nationalRoute":"prefecturalRoute"}));node.append(wrapper);
  }
  function stopAnchors(item,layout) {
    const seen=[];
    for(const sign of layout?.objects??[]) {
      if(sign.objectType!=="roadSign" || sign.signType!=="stop" || sign.linkedRoadUid!==item.uid)continue;
      const numeric=(v)=>Number.isFinite(Number(v))&&v!=null?Math.max(0,Math.min(1,Number(v))):.5;
      const anchor={x:numeric(sign.roadAnchorX),y:numeric(sign.roadAnchorY),rotation:(Number(sign.rotation)||0)-(Number(item.rotation)||0)};
      if(!seen.some(a=>Math.abs(a.x-anchor.x)<.015 && Math.abs(a.y-anchor.y)<.015 && Math.abs(a.rotation-anchor.rotation)<1))seen.push(anchor);
    }
    return seen;
  }
  function appendSurface(node,item,layout) {
    if(!roads.has(item.objectType))return;
    const w=Math.max(.5,Number(item.width)||1),h=Math.max(.5,Number(item.height)||1);
    const svg=svgRoot(w,h,"shared-road-markings");svg.setAttribute("preserveAspectRatio","none");
    const anchors=stopAnchors(item,layout);
    if(item.objectType==="road" && item.trafficDirection==="oneWay") {
      const length=Math.min(w*.25,h*1.5),thickness=Math.min(h*.12,length*.07);
      // 停止文字が中央にある場合、矢印を空いている側へ移す。
      const positions=[.5,.22,.78];
      const x=w*(positions.find(pos=>anchors.every(a=>Math.abs(a.x-pos)*w > length/2+Math.min(w*.48,h*.85)/2+1)) ?? .78),y=h/2;
      if(anchors.length === 0 || anchors.every(a=>Math.abs(a.x*w-x)>length/2+Math.min(w*.48,h*.85)/2)) svg.append(svgElement("path",{d:`M ${x-length/2} ${y} H ${x+length/2} M ${x+length*.2} ${y-length*.2} L ${x+length/2} ${y} L ${x+length*.2} ${y+length*.2}`,fill:"none",stroke:"white","stroke-width":thickness,"stroke-linejoin":"round"}));
    }
    const mw=Math.min(w*.48,h*.85),mh=Math.min(h*.65,mw*.8);
    for(const a of anchors) {
      const radians=a.rotation*Math.PI/180;
      const bx=(Math.abs(mw*Math.cos(radians))+Math.abs(mh*Math.sin(radians)))/2;
      const by=(Math.abs(mw*Math.sin(radians))+Math.abs(mh*Math.cos(radians)))/2;
      const x=Math.max(bx,Math.min(w-bx,a.x*w)),y=Math.max(by,Math.min(h-by,a.y*h));
      const g=svgElement("g",{transform:`translate(${x} ${y}) rotate(${a.rotation})`});
      g.append(svgElement("path",{d:`M ${-mw/2} ${-mh/2} H ${mw/2}`,stroke:"white","stroke-width":Math.max(.15,mh*.08)}));
      g.append(svgElement("text",{x:0,y:mh*.25,"text-anchor":"middle",fill:"white","font-size":fitLabel("止まれ",mw,mh*.8,12),"font-weight":700},"止まれ"));svg.append(g);
    }
    node.append(svg);
  }
  const markingStyles=["photoStall","full","uShape","sides","headOnly","headTicks","leftOnly","rightOnly","doubleFull","doubleSides","cornerMarks","roundedDouble","tMarks","dashed","hatched","none"];
  function appendParking(node,item) {
    const style=item.markingStyle??"photoStall";
    if(style==="none")return;
    const svg=svgRoot(100,100,"shared-photo-marking");svg.setAttribute("preserveAspectRatio","none");
    const paths={roundedDouble:"M 0 0 V 90 Q 3 100 6 90 V 0 M 94 0 V 90 Q 97 100 100 90 V 0",tMarks:"M 0 0 V 100 M 100 0 V 100 M 0 0 H 100 M 0 100 H 12 M 88 100 H 100",dashed:"M 0 0 H 100 V 100 H 0 Z",hatched:"M 0 0 H 100 V 100 H 0 Z M 0 25 L 25 0 M 0 50 L 50 0 M 0 75 L 75 0 M 0 100 L 100 0 M 25 100 L 100 25 M 50 100 L 100 50 M 75 100 L 100 75",photoStall:"M 0 100 V 0 H 100 V 100",uShape:"M 0 100 V 0 H 100 V 100",full:"M 0 0 H 100 V 100 H 0 Z",sides:"M 0 0 V 100 M 100 0 V 100",headOnly:"M 0 0 H 100",headTicks:"M 0 22 V 0 H 28 M 72 0 H 100 V 22",leftOnly:"M 0 0 V 100",rightOnly:"M 100 0 V 100",doubleFull:"M 0 0 H 100 V 100 H 0 Z M 6 6 H 94 V 94 H 6 Z",doubleSides:"M 0 0 V 100 M 6 0 V 100 M 94 0 V 100 M 100 0 V 100",cornerMarks:"M 0 22 V 0 H 28 M 72 0 H 100 V 22 M 0 78 V 100 H 28 M 72 100 H 100 V 78"};
    svg.append(svgElement("path",{d:paths[style]??paths.photoStall,fill:"none",stroke:"var(--space-line-color, white)","stroke-width":"var(--space-line-width, .35px)","vector-effect":"non-scaling-stroke"}));if(style === "dashed") svg.firstChild?.setAttribute("stroke-dasharray","6 4");
    node.append(svg);
  }
  function appendPhoto(node) { appendParking(node,{markingStyle:"photoStall"}); }
  function appendEntrance(node,item) {
    const svg=svgRoot(100,100,"shared-sign-graphic");
    svg.append(svgElement("circle",{cx:50,cy:50,r:44,fill:"#f5f3ff",stroke:"#6d28d9","stroke-width":5}));
    const text=item.objectType==="buildingEntrance"?"↑":item.accessType==="exit"?"出口":item.accessType==="entrance"?"入口":"出入口";
    svg.append(svgElement("text",{x:50,y:61,"text-anchor":"middle",fill:"#6d28d9","font-size":fitLabel(text,75,60,42),"font-weight":700},text));node.append(svg);
  }
  // まず論理座標で文字を決定し、最後に表示倍率を一度だけ掛ける。
  function typeText(item) { return item.spaceType==="custom" ? String(item.customSpaceLabel||"専用").slice(0,24) : (spacePresets[item.spaceType]?.mark||""); }
  function labelSize(item) {
    const fitted=fitLabel(item.name||"",Number(item.width)*.8,Number(item.height)*.8,18);
    return item.objectType==="building" && item.labelAutoScale===false ? Math.min(fitted,Math.max(3,Math.min(18,Number(item.labelFontSize)||6))) : fitted;
  }
  function applyTypography(node,item,scale=1) {
    const width=Number(item.width)||1,height=Number(item.height)||1;
    node.style.setProperty("--map-label-size",`${labelSize(item)*scale}px`);
    if(item.objectType === "parkingSpace") {
      const type=typeText(item), number=[groupName(item),spaceNumber(item)].filter(Boolean).join("\n");
      node.style.setProperty("--space-type-size",`${fitLabel(type,width*.9,height*.28,14)*scale}px`);
      node.style.setProperty("--space-number-size",`${fitLabel(number,width*.9,height*(type?.45:.65),18)*scale}px`);
      node.style.setProperty("--number-top",type?"48%":"18%");
      node.style.setProperty("--number-height",type?"45%":"65%");
    }
    const shield=node.querySelector?.(".shared-route-shield");
    if(shield)shield.style.width=shield.style.height=`${Math.max(.5,Math.min(width,height)*.82)*scale}px`;
  }
  function appendType(node,item) {
    const label=typeText(item);
    if(!label)return;
    const mark=document.createElement("span");mark.className="space-type-mark";mark.setAttribute("aria-hidden","true");
    if(item.spaceType!=="accessible")mark.textContent=label;
    else {
      // 国際シンボルマークに類似する単色図。OS依存の絵文字を使わない。
      const svg=svgRoot(100,100,"shared-accessible");
      svg.append(svgElement("circle",{cx:51,cy:16,r:9,fill:"currentColor"}));
      svg.append(svgElement("path",{d:"M 49 32 L 52 58 H 72 L 85 82 L 94 77 M 50 43 H 71 M 38 48 A 26 26 0 1 0 68 78",fill:"none",stroke:"currentColor","stroke-width":8,"stroke-linecap":"round","stroke-linejoin":"round"}));
      mark.append(svg);
    }
    node.append(mark);
  }
  const pavementNames={straight:"直進",left:"左折",right:"右折",straightLeft:"直進・左折",straightRight:"直進・右折",stop:"止まれ",slow:"徐行",noParking:"駐車禁止",hatched:"斜線帯",accessible:"車いすマーク",priority:"優先",ev:"EV充電",wheelStop:"車止め",walkway:"歩行者通路"};
  function appendPavement(node,item) {
    const svg=svgRoot(100,100,"shared-pavement");
    const kind=item.pavementKind||"straight", color=item.markingColor||"#ffffff";
    const path=d=>svg.append(svgElement("path",{d,fill:"none",stroke:color,"stroke-width":8,"stroke-linejoin":"miter"}));
    if(["straight","left","right","straightLeft","straightRight"].includes(kind)) {
      path("M 50 95 V 42");
      if(kind.includes("straight")){path("M 50 45 V 8 M 30 30 L 50 8 L 70 30");}
      if(kind.toLowerCase().includes("left")){path("M 50 55 Q 50 35 30 35 H 8 M 28 15 L 8 35 L 28 55");}
      if(kind.toLowerCase().includes("right")){path("M 50 55 Q 50 35 70 35 H 92 M 72 15 L 92 35 L 72 55");}
    } else if(kind==="hatched" || kind==="walkway") {
      svg.setAttribute("preserveAspectRatio","none");
      for(let n=-100;n<=100;n+=20)path(kind==="hatched"?`M ${n} 100 L ${n+100} 0`:`M 0 ${n} H 100`);
    } else if(kind==="wheelStop") {
      svg.setAttribute("preserveAspectRatio","none");
      for(const x of [8,58])svg.append(svgElement("rect",{x,y:35,width:34,height:30,rx:4,fill:"#a8adb5",stroke:"#555","stroke-width":2}));
    } else if(kind==="accessible") {
      const holder=document.createElement("div");appendType(holder,{spaceType:"accessible"});
      const symbol=holder.querySelector(".shared-accessible");if(symbol){symbol.setAttribute("class","shared-pavement");node.append(symbol);}return;
    } else {
      const text=({stop:"止まれ",slow:"徐行",noParking:"駐車禁止",priority:"優先",ev:"EV"})[kind]||"";
      svg.append(svgElement("text",{x:50,y:58,"text-anchor":"middle",fill:color,"font-weight":800,"font-size":fitLabel(text,95,80,32)},text));
    }
    node.append(svg);
  }
  function metersPerPixel(background) {
    if(!Number.isFinite(background?.centerLat)||!Number.isFinite(background?.zoom))return null;
    return Math.cos(Math.max(-85.05112878,Math.min(85.05112878,background.centerLat))*Math.PI/180)*2*Math.PI*6378137/(256*2**background.zoom);
  }
  function placeLabel(anchor,width,height,occupied,bounds) {
    const gap=8,pad=4;
    const clamp=(x,y)=>({x:Math.max(pad,Math.min(bounds.width-width-pad,x)),y:Math.max(pad,Math.min(bounds.height-height-pad,y)),width,height});
    const candidates=[clamp(anchor.x-width/2,anchor.y-height-gap),clamp(anchor.x-width/2,anchor.y+gap),clamp(anchor.x+gap,anchor.y-height/2),clamp(anchor.x-width-gap,anchor.y-height/2),clamp(pad,pad),clamp(bounds.width-width-pad,bounds.height-height-pad)];
    const overlap=(a,b)=>a.x<b.x+b.width+gap && a.x+a.width+gap>b.x && a.y<b.y+b.height+gap && a.y+a.height+gap>b.y;
    return candidates.find(a=>!occupied.some(b=>overlap(a,b)))??candidates[0];
  }
  return Object.freeze({spacePresets,spaceTypeLabel,isGuidableType,types,roads,typeText,labelSize,appendType,appendPavement,pavementNames,metersPerPixel,normalizeNumber,spaceNumber,spaceName,groupName,groupKey,fitLabel,units,numberConflict,appendSign,appendRoute,appendSurface,appendPhoto,appendParking,appendEntrance,applyTypography,markingStyles,stopAnchors,placeLabel});
})();
