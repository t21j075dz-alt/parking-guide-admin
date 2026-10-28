// 管理画面の新しいレイアウトをPC/スマホの実ブラウザで検証する。
// Playwrightがある開発環境: CHROMIUM_PATH=/path/to/chromium node tests/workspace-browser.cjs
// 外部通信はすべて遮断し、実運用のクラウドへ書き込まない。
"use strict";
const {chromium}=require("playwright");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const http=require("node:http");
const path=require("node:path");
(async()=>{
 const parent=path.resolve(__dirname,"../..");
 const server=http.createServer((request,response)=>{
  try{
   const pathname=decodeURIComponent(new URL(request.url,"http://localhost").pathname);
   if(pathname.includes(".."))throw Error("invalid path");
   let file=path.join(parent,pathname);
   if(fs.statSync(file).isDirectory())file=path.join(file,"index.html");
   const type={".js":"text/javascript",".css":"text/css",".html":"text/html",".json":"application/json"}[path.extname(file)]||"application/octet-stream";
   response.setHeader("Content-Type",type);
   response.end(fs.readFileSync(file));
  }catch{response.writeHead(404).end();}
 });
 await new Promise(ok=>server.listen(0,"127.0.0.1",ok));
 const origin="http://127.0.0.1:"+server.address().port;
 const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:["--no-sandbox","--disable-dev-shm-usage"]});
 try{
  const errors=[];
  const desktop=await browser.newPage({viewport:{width:1440,height:900}});
  desktop.on("pageerror",error=>errors.push("PC: "+error.message));
  await desktop.route("https://**/*",route=>route.abort());
  await desktop.goto(origin+"/parking-guide-admin/");
  assert.equal(await desktop.locator("body").getAttribute("data-admin-tools-open"),"false");
  assert.equal(await desktop.locator("body").getAttribute("data-admin-settings-open"),"true");
  assert.equal(await desktop.locator("#facility-select").isVisible(),true);
  assert.equal(await desktop.locator("#save-button").isVisible(),true);
  const initialWidth=await desktop.locator("#canvas-scroll").evaluate(node=>node.clientWidth);
  await desktop.locator("#admin-quick-space-add").click();
  assert.equal(await desktop.locator('.map-object[data-object-type="parkingSpace"]').count(),1);
  await desktop.locator("#undo-button").click();
  assert.equal(await desktop.locator('.map-object[data-object-type="parkingSpace"]').count(),0);
  await desktop.locator("#redo-button").click();
  assert.equal(await desktop.locator('.map-object[data-object-type="parkingSpace"]').count(),1);
  const savedBefore=await desktop.evaluate(()=>JSON.stringify(getCurrentLayout()));
  await desktop.locator("#admin-tools-toggle").click();
  assert.equal(await desktop.locator("#add-parking-space-button").isVisible(),true);
  const narrowWidth=await desktop.locator("#canvas-scroll").evaluate(node=>node.clientWidth);
  assert.ok(narrowWidth<initialWidth,"open tool panel must reduce map width");
  await desktop.locator("#admin-tools-toggle").click();
  await desktop.locator("#admin-focus-toggle").click();
  const focusWidth=await desktop.locator("#canvas-scroll").evaluate(node=>node.clientWidth);
  assert.ok(focusWidth>initialWidth,"focus mode must expand map");
  assert.equal(await desktop.locator("body").getAttribute("data-admin-settings-open"),"false");
  assert.equal(await desktop.evaluate(()=>JSON.stringify(getCurrentLayout())),savedBefore,"opening panels must not change map data");
  await desktop.locator("#admin-focus-toggle").click();
  assert.equal(await desktop.locator("body").getAttribute("data-admin-settings-open"),"true");
  await desktop.locator(".admin-header-more > summary").click();
  assert.equal(await desktop.locator("#export-json-button").isVisible(),true);
  await desktop.screenshot({path:"/tmp/parking-admin-wide-desktop.png"});
  const mobile=await browser.newPage({viewport:{width:390,height:844}});
  mobile.on("pageerror",error=>errors.push("mobile: "+error.message));
  await mobile.route("https://**/*",route=>route.abort());
  await mobile.goto(origin+"/parking-guide-admin/");
  assert.equal(await mobile.locator("body").getAttribute("data-admin-tools-open"),"false");
  assert.equal(await mobile.locator("body").getAttribute("data-admin-settings-open"),"false");
  assert.equal(await mobile.locator("#facility-select").isVisible(),true);
  const dimensions=await mobile.evaluate(()=>({screen:innerWidth,page:document.documentElement.scrollWidth}));
  assert.ok(dimensions.page<=dimensions.screen+2,"page must not overflow horizontally: "+JSON.stringify(dimensions));
  await mobile.locator("#admin-tools-toggle").click();
  assert.equal(await mobile.locator("#add-parking-space-button").isVisible(),true);
  assert.equal(await mobile.locator("body").getAttribute("data-admin-overlay"),"true");
  await mobile.locator(".admin-sidebar-backdrop").click({position:{x:385,y:300}});
  assert.equal(await mobile.locator("body").getAttribute("data-admin-tools-open"),"false");
  await mobile.locator("#admin-settings-toggle").click();
  assert.equal(await mobile.locator("#admin-settings-panel").isVisible(),true);
  await mobile.keyboard.press("Escape");
  assert.equal(await mobile.locator("body").getAttribute("data-admin-settings-open"),"false");
  await mobile.screenshot({path:"/tmp/parking-admin-wide-mobile.png"});
  assert.deepEqual(errors,[]);
  console.log("PASS: wide canvas, quick add, undo/redo, collapsible tool & inspector, focus mode, mobile drawer, no page errors");
 }finally{
  await browser.close();
  await new Promise(resolve=>server.close(resolve));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
