// User/admin integration. All external requests are intercepted; no production writes.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const server=http.createServer((req,res)=>{try{let f=path.join(root,new URL(req.url,'http://localhost').pathname);if(fs.statSync(f).isDirectory())f=path.join(f,'index.html');res.setHeader('Content-Type',({'.js':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json'})[path.extname(f)]||'application/octet-stream');res.end(fs.readFileSync(f));}catch{res.writeHead(404).end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 try {
  const page=await browser.newPage({viewport:{width:390,height:844}}), errors=[];page.on('pageerror',e=>errors.push(e.message));
  page.setDefaultTimeout(10000);
  let stale=false;
  const jpeg='/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAX/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdAAB//9k=';
  await page.route('https://**/*',route=>{
   const url=route.request().url();
   if(url.includes('/parking_camera_public?'))return route.fulfill({json:[{camera_id:'USB Camera',captured_at:new Date(Date.now()-(stale?400000:0)).toISOString(),image_data:'data:image/jpeg;base64,'+jpeg}]});
   if(url.includes('/rest/v1/'))return route.fulfill({json:[]});
   return route.abort();
  });
  const origin='http://127.0.0.1:'+server.address().port;
  await page.goto(origin+'/parking-guide-user/');
  await page.evaluate(()=>{
   const f=FACILITIES.find(f=>f.operatingStatus!=='opening-scheduled');
   window.PARKING_LAYOUTS={...window.PARKING_LAYOUTS,[f.layoutId||f.id]:{facilityId:f.id,facilityIdentityKey:getFacilityIdentityKeyForUser(f),canvas:{width:100,height:100},operations:{hoursLabel:'09:00–21:00',closed:true},objects:[]}};
   state.selectedFacility=f;renderFacilities();
  });
  assert.equal(await page.locator('.availability-closed').count(),1);
  assert.ok((await page.locator('.facility-hours').first().textContent()).includes('09:00'));
  await page.locator('[data-facility-id]').first().click();
  await page.waitForFunction(()=>!document.querySelector('#facility-camera img').hidden).catch(async e=>{console.log(await page.evaluate(()=>({screen:state.currentScreen,status:document.querySelector('#facility-camera [role=status]').textContent,errors:document.querySelector('#facility-camera').outerHTML})));console.log(errors);throw e;});
  assert.ok((await page.locator('#facility-camera [role=status]').textContent()).includes('撮影'));
  stale=true;await page.locator('#facility-camera button').click();
  await page.waitForFunction(()=>document.querySelector('#facility-camera img').hidden);
  assert.equal(await page.evaluate(()=>prepareSpaces(state.selectedFacility).spaces.length),0);
  await page.screenshot({path:process.env.PARKING_SCREENSHOT || '/tmp/parking-experience-mobile.png',fullPage:true});
  const admin=await browser.newPage({viewport:{width:1440,height:1000}});admin.on('pageerror',e=>errors.push(e.message));await admin.route('https://**/*',r=>r.abort());
  await admin.goto(origin+'/parking-guide-admin/');
  await admin.getByRole('button',{name:'営業時間・休業・共用区画',exact:true}).click();
  await admin.locator('#facility-hours-label').fill('24時間');await admin.locator('#facility-closed').check();await admin.locator('#save-facility-operation').click();
  assert.equal(await admin.evaluate(()=>getCurrentLayout().operations.closed),true);
  await admin.locator('#close-facility-editor').click();
  await admin.locator('#add-parking-space-button').click();
  await admin.getByRole('button',{name:'営業時間・休業・共用区画',exact:true}).click();
  await admin.waitForFunction(()=>!document.querySelector('#save-shared-group').disabled);
  await admin.locator('#space-shared-group').fill('shared-A');await admin.locator('#save-shared-group').click();
  assert.equal(await admin.evaluate(()=>getSelectedObject().sharedGroup),'shared-A');
  await admin.locator('#close-facility-editor').click();
  const snap=await admin.evaluate(()=>{
   const layout=getCurrentLayout();layout.objects=[{uid:'a',objectType:'parkingSpace',x:100,y:100,width:25,height:50,rotation:90}];
   elements.snapEnabled.checked=true;elements.parkingSnapStrong.checked=true;state.viewScale=1;
   const item={uid:'b',objectType:'parkingSpace',width:20,height:40,rotation:90};
   const snapped=snapParkingSpacePosition(item,108,128);
   elements.snapEnabled.checked=false;const free=snapObjectPosition(item,110.2,119.3);
   return {snapped,free};
  });
  // Centre-based rotation: adjacent left edges become x=107.5,y=127.5.
  assert.equal(snap.snapped.x,107.5);assert.equal(snap.snapped.y,127.5);
  assert.equal(snap.free.x,110.2);assert.equal(snap.free.y,119.3);
  await admin.screenshot({path:'/tmp/parking-experience-admin.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('PASS: closed/hours, pre-search photo, stale photo hiding, admin settings, shared group, rotated snap and snap OFF');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
