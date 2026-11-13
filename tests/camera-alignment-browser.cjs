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
    let simulateNetworkFailure=false;
    await page.route("https://**/*",route=>{
      const url=route.request().url();
      if(simulateNetworkFailure)return route.abort();
      if(url.includes("/rest/v1/parking_live_visibility"))
        return route.fulfill({json:[{is_published:false}]});
      if(url.includes("/rest/v1/parking_live_status"))
        return route.fulfill({json:[
          {space_uid:"space_001",status:"available",checked_at:new Date(Date.now()-1000).toISOString()},
          {space_uid:"space_002",status:"occupied",checked_at:new Date(Date.now()-35000).toISOString()},
        ]});
      if(url.includes("/rest/v1/parking_vehicle_sessions"))
        return route.fulfill({json:[]});
      return route.abort();
    });
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
    const pair=[[.12,.15],[.88,.15],[.88,.84],[.12,.84],[.47,.32],[.68,.65]];
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
    assert.equal(await page.locator("#alignment-point-count").textContent(),"対応点 6 / 最大24組");
    assert.equal(await page.locator("#alignment-point-list li").count(),6);
    assert.equal(await page.locator("#alignment-project").isEnabled(),true);
    await page.locator("#alignment-project").click();
    assert.equal(await page.locator("#alignment-camera-overlay polygon").count(),2);
    assert.match(await page.locator("#alignment-quality").textContent(),/採用6点/);
    assert.equal(await page.locator("#alignment-export").isEnabled(),false);
    // A deliberately mismatched seventh pair must be flagged, not silently exported.
    await page.evaluate(()=>{
      function choose(id,nx,ny,isMap){
        const svg=document.getElementById(id);
        const p=svg.createSVGPoint();
        p.x=isMap?nx*getCurrentLayout().canvas.width:nx;
        p.y=isMap?ny*getCurrentLayout().canvas.height:ny;
        const location=p.matrixTransform(svg.getScreenCTM());
        svg.dispatchEvent(new MouseEvent("click",{clientX:location.x,clientY:location.y,bubbles:true}));
      }
      choose("alignment-map",.36,.68,true);
      choose("alignment-camera-overlay",.92,.13,false);
    });
    assert.equal(await page.locator("#alignment-point-list li").count(),7);
    await page.locator("#alignment-project").click();
    assert.match(await page.locator("#alignment-outlier-count").textContent(),/誤差大 1点/);
    assert.equal(await page.locator("#alignment-confirm-visual").isDisabled(),true);
    assert.equal(await page.locator("#alignment-export").isEnabled(),false);
    await page.locator("#alignment-point-details summary").click();
    await page.getByRole("button",{name:"位置合わせ点7を削除"}).click();
    await page.locator("#alignment-project").click();
    assert.match(await page.locator("#alignment-quality").textContent(),/採用6点/);
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
    assert.equal(output.map_points.length,6);
    assert.equal(output.image_points.length,6);
    assert.equal(output.alignment_quality.method,"ransac-least-squares");
    assert.equal(output.alignment_quality.point_count,6);
    assert.deepEqual(output.alignment_quality.outlier_indices,[]);
    await page.screenshot({path:"/tmp/parking-camera-alignment-desktop.png",fullPage:true});

    await page.locator("#alignment-close").click();
    // Main view shortcuts open existing tool panels, not new copies.
    await page.evaluate(()=>{state.remoteAccessToken="synthetic-local-ui-test-token";});
    await page.locator('#admin-camera-shortcuts [data-action="monitor"]').click();
    assert.equal(await page.locator("#live-monitor-panel").getAttribute("open"),"");
    assert.equal(await page.locator("#live-monitor-stats").count(),1);
    assert.equal(await page.locator("#live-monitor-filter").count(),1);
    await page.waitForFunction(()=>document.querySelector("#live-stat-available")?.textContent==="1");
    // A 35-second-old 'occupied' report must not be shown as current.
    assert.equal(await page.locator("#live-stat-occupied").textContent(),"0");
    assert.equal(await page.locator("#live-stat-unknown").textContent(),"1");
    await page.locator("#live-monitor-filter").selectOption("unknown");
    assert.equal(await page.locator("#live-monitor-spaces li").count(),2);
    assert.equal(await page.locator("#live-monitor-spaces li:not([hidden])").count(),1);
    assert.equal(await page.locator("#live-monitor-spaces li:not([hidden])").getAttribute("data-live-status"),"unknown");
    simulateNetworkFailure=true;
    await page.locator("#live-monitor-refresh").click();
    await page.waitForFunction(()=>document.querySelector("#live-stat-available")?.textContent==="—");
    assert.equal(await page.locator("#live-monitor-spaces li").count(),0);
    assert.equal(await page.locator("#live-monitor-published").isEnabled(),false);

    // Full photo-first flow on Nikko: no homography points are required.
    await page.evaluate(()=>{
      state.facilityId="nikko-test-001";
      state.layouts["nikko-test-001"]={
        facilityId:"nikko-test-001",canvas:{width:1800,height:1200},
        objects:[
          {uid:"space_001",objectType:"parkingSpace",x:250,y:250,width:100,height:140,spaceNumber:"1"},
          {uid:"space_002",objectType:"parkingSpace",x:450,y:250,width:100,height:140,spaceNumber:"2"},
          {uid:"space_003",objectType:"parkingSpace",x:650,y:250,width:100,height:140,spaceNumber:"3",
           cameraCoverage:"outside"},
        ],
      };
      document.dispatchEvent(new Event("parking:open-camera-alignment"));
    });
    assert.equal(await page.locator("#alignment-photo-editor").isVisible(),true);
    await page.locator("#alignment-file").setInputFiles({
      name:"camera.png",mimeType:"image/png",buffer:Buffer.from(png,"base64"),
    });
    await page.waitForFunction(()=>document.querySelector("#alignment-photo-ready")?.dataset?.ready==="true");
    await page.locator("#alignment-zone-method").selectOption("manual");
    await page.locator("#alignment-slot-select").selectOption("space_001");
    await page.locator("#alignment-draw-zone").click();
    for(const point of [[.20,.26],[.34,.26],[.34,.44],[.20,.44]]){
      await page.evaluate(([x,y])=>{
        const svg=document.querySelector("#alignment-camera-overlay");
        const p=svg.createSVGPoint();p.x=x;p.y=y;
        const screen=p.matrixTransform(svg.getScreenCTM());
        svg.dispatchEvent(new MouseEvent("click",{clientX:screen.x,clientY:screen.y,bubbles:true}));
      },point);
    }
    assert.match(await page.locator("#alignment-photo-editor-count").textContent(),/1件/);
    assert.equal(await page.locator("#alignment-camera-overlay polygon[data-zone-uid]").count(),1);
    assert.equal(await page.locator("#alignment-camera-overlay circle[data-zone-corner]").count(),4);
    assert.equal(await page.locator("#alignment-export").isEnabled(),false);
    await page.locator("#alignment-confirm-visual").check();
    const [manualDownload]=await Promise.all([
      page.waitForEvent("download"),page.locator("#alignment-export").click()
    ]);
    const manualOutput=JSON.parse(fs.readFileSync(await manualDownload.path(),"utf-8"));
    assert.equal(manualOutput.alignment_method,"manual-zones");
    assert.deepEqual(manualOutput.map_points,[]);
    assert.deepEqual(manualOutput.space_uids,["space_001"]);
    assert.deepEqual(manualOutput.excluded_space_uids,["space_002","space_003"]);
    assert.deepEqual(manualOutput.manual_zone_uids,["space_001"]);
    await page.locator("#alignment-clear-zone").click();
    assert.equal(await page.locator("#alignment-camera-overlay polygon[data-zone-uid]").count(),0);
    assert.equal(await page.locator("#alignment-export").isDisabled(),true);
    await page.locator("#alignment-close").click();

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
    console.log("PASS: 6-point and photo-first mapping, safe out-of-frame UID exclusion, desktop/mobile UI");
  } finally {
    await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
})().catch(error=>{console.error(error);process.exitCode=1;});
