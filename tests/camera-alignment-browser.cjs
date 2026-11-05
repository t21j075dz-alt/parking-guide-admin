// Camera-map alignment UI smoke test in real Chromium.
// No remote request succeeds and no Supabase or camera write is made.
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const http=require("node:http");
const {chromium}=require("playwright");

(async()=>{
  const root=path.resolve(__dirname,"../..");
  const server=http.createServer((request,response)=>{
    try{
      const pathname=decodeURIComponent(new URL(request.url,"http://localhost").pathname);
      if(pathname.includes(".."))throw Error("invalid path");
      let file=path.join(root,pathname);
      if(fs.statSync(file).isDirectory())file=path.join(file,"index.html");
      const type={".html":"text/html",".js":"text/javascript",".css":"text/css",".json":"application/json"}[path.extname(file)]||"application/octet-stream";
      response.setHeader("Content-Type",type);
      response.end(fs.readFileSync(file));
    }catch{response.writeHead(404).end();}
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const browser=await chromium.launch({
    headless:true,
    ...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),
    args:["--no-sandbox","--disable-dev-shm-usage"],
  });
  const errors=[];
  try{
    const origin="http://127.0.0.1:"+server.address().port;
    const page=await browser.newPage({viewport:{width:1510,height:970},acceptDownloads:true});
    page.on("pageerror",error=>errors.push("desktop: "+error.message));
    await page.route("https://**/*",route=>route.abort());
    await page.goto(origin+"/parking-guide-admin/");
    const align=page.locator('#admin-camera-shortcuts [data-action="alignment"]');
    assert.equal(await align.isVisible(),true,"workspace shortcut must remain visible");
    await page.evaluate(()=>{
      const layout=getCurrentLayout();
      layout.objects=[
        {uid:"space_001",objectType:"parkingSpace",x:600,y:350,width:140,height:200,rotation:0,spaceNumber:"001"},
        {uid:"space_002",objectType:"parkingSpace",x:850,y:350,width:140,height:200,rotation:25,spaceNumber:"002"},
      ];
      render();
    });
    await page.waitForFunction(()=>document.querySelector("#admin-camera-space-count")?.textContent?.includes("2区画"));
    await align.click();
    assert.equal(await page.locator("#camera-map-alignment-dialog").isVisible(),true);
    assert.equal(await page.locator("#alignment-steps li.is-current").count(),1);
    assert.equal(await page.locator("#alignment-steps li.is-current").getAttribute("data-alignment-step"),"photo");
    assert.equal(await page.locator("#alignment-export").isEnabled(),false);
    assert.equal(await page.locator("#alignment-space-count").textContent(),"登録区画 2件");

    const zoom=page.locator("#alignment-map-zoom");
    const fitting=await page.locator("#alignment-map").getAttribute("viewBox");
    await zoom.click();
    const whole=await page.locator("#alignment-map").getAttribute("viewBox");
    assert.equal(whole,"0 0 1800 1200");
    assert.notEqual(fitting,whole,"default map should zoom into parking spaces");

    const png=await page.evaluate(()=>{
      const c=document.createElement("canvas");
      c.width=640;c.height=480;
      const context=c.getContext("2d");
      context.fillStyle="#64748b";context.fillRect(0,0,640,480);
      context.strokeStyle="#ffffff";context.lineWidth=7;
      context.strokeRect(140,110,350,250);
      return c.toDataURL("image/png").split(",")[1];
    });
    await page.locator("#alignment-file").setInputFiles({
      name:"camera.png",mimeType:"image/png",buffer:Buffer.from(png,"base64"),
    });
    await page.waitForFunction(()=>document.querySelector("#alignment-photo-ready")?.dataset?.ready==="true");
    assert.equal(await page.locator("#alignment-image-info").textContent(),"写真 640 × 480 px");
    assert.equal(await page.locator("#alignment-steps li.is-current").getAttribute("data-alignment-step"),"points");
    const pair=[[.12,.15],[.88,.15],[.88,.84],[.12,.84]];
    for(const [x,y] of pair){
      await page.evaluate(([nx,ny])=>{
        const svg=document.querySelector("#alignment-map");
        const p=svg.createSVGPoint();
        p.x=nx*getCurrentLayout().canvas.width;
        p.y=ny*getCurrentLayout().canvas.height;
        const screen=p.matrixTransform(svg.getScreenCTM());
        svg.dispatchEvent(new MouseEvent("click",{clientX:screen.x,clientY:screen.y,bubbles:true}));
      },[x,y]);
      await page.evaluate(([nx,ny])=>{
        const svg=document.querySelector("#alignment-camera-overlay");
        const p=svg.createSVGPoint();p.x=nx;p.y=ny;
        const screen=p.matrixTransform(svg.getScreenCTM());
        svg.dispatchEvent(new MouseEvent("click",{clientX:screen.x,clientY:screen.y,bubbles:true}));
      },[x,y]);
    }
    assert.equal(await page.locator("#alignment-point-count").textContent(),"対応点 4 / 4 組");
    assert.equal(await page.locator("#alignment-project").isEnabled(),true);
    await page.locator("#alignment-project").click();
    assert.equal(await page.locator("#alignment-camera-overlay polygon").count(),2);
    assert.equal(await page.locator("#alignment-export").isEnabled(),false);
    await page.locator("#alignment-confirm-visual").check();
    assert.equal(await page.locator("#alignment-export").isEnabled(),true);
    const [download]=await Promise.all([
      page.waitForEvent("download"),
      page.locator("#alignment-export").click(),
    ]);
    const output=JSON.parse(fs.readFileSync(await download.path(),"utf-8"));
    assert.deepEqual(output.space_uids,["space_001","space_002"]);
    assert.equal(Object.keys(output.space_zones).length,2);
    assert.equal(output.image_width,640);
    await page.screenshot({path:"/tmp/parking-camera-alignment-desktop.png",fullPage:true});

    await page.locator("#alignment-close").click();
    // Main view shortcuts open existing tool panels, not new copies.
    await page.locator('#admin-camera-shortcuts [data-action="monitor"]').click();
    assert.equal(await page.locator("#live-monitor-panel").getAttribute("open"),"");
    assert.equal(await page.locator("#live-monitor-stats").count(),1);
    assert.equal(await page.locator("#live-monitor-filter").count(),1);

    const mobile=await browser.newPage({viewport:{width:390,height:844}});
    mobile.on("pageerror",error=>errors.push("mobile: "+error.message));
    await mobile.route("https://**/*",route=>route.abort());
    await mobile.goto(origin+"/parking-guide-admin/");
    assert.equal(await mobile.locator('#admin-camera-shortcuts [data-action="alignment"]').isVisible(),true);
    await mobile.locator('#admin-camera-shortcuts [data-action="alignment"]').click();
    assert.equal(await mobile.locator("#camera-map-alignment-dialog").isVisible(),true);
    const widths=await mobile.evaluate(()=>{
      const dialog=document.querySelector("#camera-map-alignment-dialog");
      return {client:dialog.clientWidth,scroll:dialog.scrollWidth,screen:innerWidth,body:document.documentElement.scrollWidth};
    });
    assert.ok(widths.scroll<=widths.client+2,"mobile dialog horizontal overflow: "+JSON.stringify(widths));
    assert.ok(widths.body<=widths.screen+2,"mobile page horizontal overflow: "+JSON.stringify(widths));
    await mobile.screenshot({path:"/tmp/parking-camera-alignment-mobile.png"});
    assert.deepEqual(errors,[],"no browser runtime errors");
    console.log("PASS: desktop/mobile camera-map UI, viewport, four pairs, approval/download, monitor shortcuts");
  } finally {
    await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
