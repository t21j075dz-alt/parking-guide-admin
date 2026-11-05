"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const {homography,project,parkingCorners,generateZones,layoutSignature,parkingViewport}=require("../camera-map-alignment-core.js");

const anchors=[[.1,.1],[.9,.1],[.9,.9],[.1,.9]];
const camera=[[.16,.12],[.78,.20],[.91,.85],[.07,.88]];
const layout={
  facilityId:"home-test-001",
  canvas:{width:1000,height:1000},
  objects:[
    {uid:"space_001",objectType:"parkingSpace",x:200,y:200,width:120,height:250,rotation:0},
    {uid:"space_002",objectType:"parkingSpace",x:400,y:200,width:120,height:250,rotation:90},
  ],
};
test("four-point perspective mapping preserves all calibration anchors",()=>{
  const matrix=homography(anchors,camera);
  for(let i=0;i<4;i++){
    const result=project(matrix,anchors[i]);
    for(let j=0;j<2;j++)assert.ok(Math.abs(result[j]-camera[i][j])<1e-8);
  }
});
test("rotated administrator parking geometry is respected",()=>{
  const corners=parkingCorners({objectType:"parkingSpace",x:10,y:20,width:20,height:40,rotation:90});
  assert.deepEqual(corners.map(p=>p.map(v=>Math.round(v))),[[40,30],[40,50],[0,50],[0,30]]);
});
test("all map slots export the exact UID and normalized projected quadrilaterals",()=>{
  const generated=generateZones(layout,anchors,camera);
  assert.deepEqual(generated.space_uids,["space_001","space_002"]);
  assert.equal(Object.keys(generated.space_zones).length,2);
  for(const poly of Object.values(generated.space_zones)){
    assert.equal(poly.length,4);
    for(const [x,y] of poly)assert.ok(x>=0&&x<=1&&y>=0&&y<=1);
  }
  assert.deepEqual(layout.objects[0].x,200); // input is never changed
});
test("degenerate anchors and missing spaces are rejected",()=>{
  assert.throws(()=>homography([[0,0],[.2,.2],[.4,.4],[.8,.8]],camera),/4点|一直線/);
  assert.throws(()=>generateZones({...layout,objects:[]},anchors,camera),/駐車区画/);
});
test("a projected space outside the image is never exported or silently clipped",()=>{
  const outside={...layout,objects:[{uid:"space_100",objectType:"parkingSpace",x:980,y:980,width:150,height:150}]};
  assert.throws(()=>generateZones(outside,anchors,camera),/撮影範囲外/);
});
test("duplicate parking IDs are rejected",()=>{
  const duplicate={...layout,objects:[layout.objects[0],{...layout.objects[0]}]};
  assert.throws(()=>generateZones(duplicate,anchors,camera),/重複/);
});

test("a map edit changes the alignment review signature and reprojects new geometry",()=>{
  const before=layoutSignature(layout);
  const changed=JSON.parse(JSON.stringify(layout));
  changed.objects[0].x+=30;
  assert.notEqual(layoutSignature(changed),before);
  assert.deepEqual(layoutSignature({...layout,objects:layout.objects.slice().reverse()}),before);
  const first=generateZones(layout,anchors,camera).space_zones.space_001;
  const next=generateZones(changed,anchors,camera).space_zones.space_001;
  assert.notDeepEqual(first,next);
  // Original map remains unchanged; the same four anchors can reproject edited slots.
  assert.equal(layout.objects[0].x,200);
});


test("large map focuses parking slots and a full-map toggle remains possible",()=>{
  const full={canvas:{width:1800,height:1200},objects:[
    {uid:"space_001",objectType:"parkingSpace",x:880,y:540,width:26,height:50,rotation:0},
    {uid:"space_002",objectType:"parkingSpace",x:916,y:540,width:26,height:50,rotation:90},
  ]};
  const viewport=parkingViewport(full);
  assert.ok(viewport.width<1800 && viewport.height<1200,"slots should be visually enlarged");
  for(const slot of full.objects)for(const [x,y] of parkingCorners(slot)){
    assert.ok(x>=viewport.x-1e-8 && x<=viewport.x+viewport.width+1e-8);
    assert.ok(y>=viewport.y-1e-8 && y<=viewport.y+viewport.height+1e-8);
  }
  // Mouse position in SVG user coordinates is divided by full canvas size, not viewport size.
  const pixel=[900,565];
  assert.deepEqual(pixel.map((v,i)=>v/[1800,1200][i]),[.5,565/1200]);
});

test("empty or malformed maps use safe full map bounds",()=>{
  const whole=parkingViewport({canvas:{width:1800,height:1200},objects:[]});
  assert.deepEqual(whole,{x:0,y:0,width:1800,height:1200});
  assert.throws(()=>parkingViewport({canvas:{width:0,height:1200},objects:[]}),/不正/);
  assert.deepEqual(parkingViewport({canvas:{width:1800,height:1200},objects:[
    {uid:"bad",objectType:"parkingSpace",x:10,y:10,width:0,height:80}
  ]}),{x:0,y:0,width:1800,height:1200});
});


test("Nikko alignment keeps every visible parking slot but never reports out-of-frame spaces as free",()=>{
  const map={facilityId:"nikko-test-001",canvas:{width:1000,height:1000},objects:[
    {uid:"space_001",objectType:"parkingSpace",x:150,y:180,width:80,height:150,rotation:0},
    {uid:"space_002",objectType:"parkingSpace",x:320,y:180,width:80,height:150,rotation:0},
    {uid:"space_009",objectType:"parkingSpace",x:510,y:180,width:80,height:150,rotation:0},
    {uid:"space_044",objectType:"parkingSpace",x:1020,y:500,width:80,height:150,rotation:0},
  ]};
  const actual=[[0,0],[1,0],[1,1],[0,1]];
  const result=generateZones(map,actual,actual,{skipOutsideFrame:true});
  assert.deepEqual(result.space_uids,["space_001","space_002","space_009"]);
  assert.deepEqual(result.excluded_space_uids,["space_044"]);
  assert.equal(Object.keys(result.space_zones).length,3);
  assert.equal(Object.hasOwn(result.space_zones,"space_044"),false);
  assert.equal(map.objects.length,4,"full facility map must stay intact");
  assert.throws(()=>generateZones(map,actual,actual),/撮影範囲外/);
});

test("Nikko alignment refuses a camera that sees zero complete parking spaces",()=>{
  const map={canvas:{width:1000,height:1000},objects:[
    {uid:"space_100",objectType:"parkingSpace",x:1300,y:1100,width:60,height:110,rotation:0}
  ]};
  const actual=[[0,0],[1,0],[1,1],[0,1]];
  assert.throws(()=>generateZones(map,actual,actual,{skipOutsideFrame:true}),/駐車区画がありません/);
});
