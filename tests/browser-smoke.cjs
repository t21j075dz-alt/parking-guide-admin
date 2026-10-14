// Playwrightを導入した開発環境で実行。兄弟ディレクトリに利用者リポジトリを置く。
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),http=require('node:http');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost'),file=path.join(root,decodeURIComponent(url.pathname));try{const f=fs.statSync(file).isDirectory()?path.join(file,'index.html'):file;const ext=path.extname(f);res.setHeader('Content-Type',({'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json'})[ext]||'application/octet-stream');res.end(fs.readFileSync(f));}catch{res.statusCode=404;res.end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const origin=`http://127.0.0.1:${server.address().port}`;
 const b=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
 try{
 const page=await b.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('https://**/*',r=>r.abort());
 await page.goto(origin+'/parking-guide-admin/');
 await page.click('#add-parking-space-button');assert.equal(await page.locator('.map-object[data-object-type="parkingSpace"]').count(),1);
 await page.click('#undo-button');assert.equal(await page.locator('.map-object[data-object-type="parkingSpace"]').count(),0);
 await page.click('#redo-button');assert.equal(await page.locator('.map-object[data-object-type="parkingSpace"]').count(),1);
 await page.click('.map-object[data-object-type="parkingSpace"]');
 await page.fill('#width-meters','3');await page.fill('#height-meters','6');await page.click('#apply-meters-button');
 assert.ok(await page.evaluate(()=>Math.abs(getSelectedObject().width*getLayoutScale(getCurrentLayout())-3)<1e-6));
 await page.click('#undo-button');assert.ok(await page.evaluate(()=>Math.abs(getCurrentLayout().objects[0].width*getLayoutScale(getCurrentLayout())-2.5)<1e-6));await page.click('#redo-button');
 await page.click('.map-object[data-object-type="parkingSpace"]');
 const before=await page.evaluate(()=>({w:getSelectedObject().width,h:getSelectedObject().height,font:parseFloat(document.querySelector('.space-number-mark').style.fontSize||getComputedStyle(document.querySelector('.space-number-mark')).fontSize)}));
 const box=await page.locator('.resize-handle--e').boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.mouse.move(box.x+box.width/2+30,box.y+box.height/2,{steps:5});await page.mouse.up();
 const after=await page.evaluate(()=>({w:getSelectedObject().width,h:getSelectedObject().height}));assert.ok(after.w>before.w);assert.equal(after.h,before.h);
 // Type changes must use physical dimensions too.
 await page.selectOption('#space-type','accessible');assert.ok(await page.evaluate(()=>Math.abs(getSelectedObject().width*getLayoutScale(getCurrentLayout())-3.5)<1e-6));assert.equal(await page.locator('.shared-accessible').count(),1);
 await page.selectOption('#new-parking-space-type','priority');await page.click('#add-parking-space-button');
 await page.evaluate(()=>{const layout=getCurrentLayout();layout.background=null;layout.canvas.scaleSource='manual';layout.objects=[];for(let i=0;i<8;i++){addObject('parkingSpace',{spaceType:['standard','compact','accessible','ev','priority'][i%5]});const o=getSelectedObject();o.x=700+i*32;o.y=500;o.rotation=i===7?30:0;o.markingStyle=i%2?'roundedDouble':'photoStall';o.spaceGroup='A';o.spaceNumber=String(i+1);}addObject('building');Object.assign(getSelectedObject(),{x:700,y:410,width:220,height:55,name:'店舗入口のある建物',polygonPoints:[{x:0,y:0},{x:220,y:0},{x:220,y:55},{x:0,y:55}]});addObject('buildingEntrance');Object.assign(getSelectedObject(),{x:805,y:470});addObject('pavementMarking',{pavementKind:'straight'});Object.assign(getSelectedObject(),{x:780,y:570,width:20,height:50});saveLocal();render();window.ParkingEditor.fitObjects();});
 await page.screenshot({path:'/tmp/parking-admin-desktop.png'});
 const layout=await page.evaluate(()=>structuredClone(getCurrentLayout()));
 const oldId=layout.facilityId;await page.selectOption('#facility-select',{index:1});await page.click('#add-parking-space-button');await page.click('#undo-button');assert.equal(await page.evaluate(()=>getCurrentLayout().objects.length),0);await page.selectOption('#facility-select',oldId);assert.equal(await page.evaluate(()=>getCurrentLayout().objects.length),layout.objects.length);
 await page.reload();assert.ok(await page.evaluate(()=>Object.values(state.layouts).some(l=>l.objects.length===11)));
 await page.setViewportSize({width:1024,height:768});await page.screenshot({path:'/tmp/parking-admin-tablet.png'});
 // User renderer receives the exact admin JSON in an isolated test browser.
 const user=await b.newPage({viewport:{width:390,height:844}});user.on('pageerror',e=>errors.push(e.message));await user.route('https://**/*',r=>r.abort());await user.goto(origin+'/parking-guide-user/');
 await user.evaluate(layout=>{document.querySelectorAll('.screen').forEach(n=>n.hidden=true);const map=document.querySelector('#parking-map');let parent=map;while(parent){parent.hidden=false;parent.classList?.remove('hidden');parent=parent.parentElement;}state.guideEntrance=layout.objects.find(o=>o.objectType==='buildingEntrance');renderRegisteredLayout(layout,null);document.querySelector('#launch-screen')?.remove();},layout);
 await user.locator('#parking-map').scrollIntoViewIfNeeded();assert.equal(await user.locator('[data-object-type="parkingSpace"]').count(),8);assert.equal(await user.locator('.shared-accessible').count(),2);assert.equal(await user.locator('[data-object-type="pavementMarking"] svg').count(),1);
 await user.locator('#parking-map').screenshot({path:'/tmp/parking-user-map.png'});
 await user.evaluate(layout=>{const o=layout.objects.find(o=>o.objectType==='parkingSpace');state.guideEntrance=layout.objects.find(o=>o.objectType==='buildingEntrance');renderRegisteredLayout(layout,{uid:o.uid,id:mapDisplay.spaceName(o),sourceObject:o});},layout);
 await user.locator('#parking-map').screenshot({path:'/tmp/parking-user-focus.png'});
 // 任意の実データはローカルファイルから読み、ネットワークへ書き戻さない。
 if(process.env.PARKING_LAYOUT_FIXTURE){
  const rows=JSON.parse(fs.readFileSync(process.env.PARKING_LAYOUT_FIXTURE,'utf8'));
  for(const row of rows){
   const preserved=await page.evaluate(row=>{
    validateLayoutCollection({[row.facility_id]:row.layout_data});
    state.layouts[row.facility_id]=structuredClone(row.layout_data);state.facilityId=row.facility_id;state.selectedUid=null;
    const facility=state.facilities.find(f=>f.id===row.facility_id)||getExperimentFacility();
    ensureLayoutMatchesFacility(facility);render();window.ParkingEditor.fitObjects();
    const geometry=l=>l.objects.map(o=>({uid:o.uid,x:o.x,y:o.y,width:o.width,height:o.height,rotation:o.rotation,polygonPoints:o.polygonPoints}));
    return JSON.stringify(geometry(getCurrentLayout()))===JSON.stringify(geometry(row.layout_data)) && getCurrentLayout().canvas.scaleMetersPerPixel===row.layout_data.canvas.scaleMetersPerPixel;
   },row);
   assert.ok(preserved,'Saved layout geometry and scale must remain unchanged');
   await user.evaluate(layout=>{state.guideEntrance=layout.objects.find(o=>o.objectType==='buildingEntrance');renderRegisteredLayout(layout,null);},row.layout_data);
   assert.equal(await user.locator('[data-object-type="parkingSpace"]').count(),row.layout_data.objects.filter(o=>o.objectType==='parkingSpace').length);
  }
  console.log(`PASS: ${rows.length} saved layouts preserve geometry/scale and render in both apps`);
 }
 // 全区画の選択・生成・復元と利用者の追加条件を実操作で確認。
 assert.equal(await page.locator('#new-parking-space-type option').count(),46);
 const allTypes=await page.evaluate(()=>Object.keys(mapDisplay.spacePresets));
 await page.evaluate(()=>{getCurrentLayout().objects=[];getCurrentLayout().background=null;state.selectedUid=null;render();});
 for(const type of allTypes){await page.selectOption('#new-parking-space-type',type);await page.click('#add-parking-space-button');}
 assert.equal(await page.evaluate(()=>getCurrentLayout().objects.length),46);
 await page.fill('#space-custom-label','福祉送迎専用');await page.locator('#space-custom-label').blur();
 assert.equal(await page.evaluate(()=>getSelectedObject().customSpaceLabel),'福祉送迎専用');
 const extendedLayout=await page.evaluate(()=>structuredClone(getCurrentLayout()));
 await page.evaluate(async()=>{const json=JSON.stringify(state.layouts);await importJson({text:async()=>json});});
 assert.equal(await page.evaluate(()=>getCurrentLayout().objects.length),46);
 await user.evaluate(layout=>{state.guideEntrance=null;renderRegisteredLayout(layout,null);},extendedLayout);
 assert.equal(await user.locator('[data-object-type="parkingSpace"]').count(),46);
 assert.equal(await user.evaluate(layout=>createLayoutParkingSpaces(layout,{id:layout.facilityId}).length,extendedLayout),40);
 await user.evaluate(()=>{document.querySelectorAll('.screen').forEach(n=>n.hidden=true);document.querySelector('#condition-screen').hidden=false;updateExtendedSpaceTypes();});
 assert.equal(await user.locator('#extended-space-type option').count(),35);
 await user.selectOption('#extended-space-type','bus');
 assert.ok(await user.locator('input[name="spaceType"][value="extended"]').isChecked());
 await user.evaluate(()=>saveSearchConditions());assert.equal(await user.evaluate(()=>state.requestedSpaceType),'bus');
 await user.evaluate(()=>{state.language='en';updateExtendedSpaceTypes();});
 assert.equal(await user.locator('#extended-space-type').inputValue(),'bus');
 assert.equal(await user.locator('#extended-space-type option[value="bus"]').textContent(),'Bus only');
 await user.screenshot({path:'/tmp/parking-user-types.png'});
 console.log('PASS: 46 types create/import/render, 40 eligible search types, custom label, bus choice and English labels');
 assert.deepEqual(errors,[]);console.log('PASS: add, undo/redo, meters, live resize, type resize, priority, facility isolation, reload, 1024/1440px admin and 390px user map; no page errors');
 }finally{await b.close();server.close();}
})().catch(e=>{console.error(e);process.exit(1)});
