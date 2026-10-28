// Integration: no external requests or production writes.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const server=http.createServer((req,res)=>{try{let f=path.join(root,new URL(req.url,'http://localhost').pathname);if(fs.statSync(f).isDirectory())f=path.join(f,'index.html');res.setHeader('Content-Type',({'.js':'text/javascript','.html':'text/html','.css':'text/css'})[path.extname(f)]||'application/json');res.end(fs.readFileSync(f));}catch{res.writeHead(404).end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage']});
 try{
  const origin='http://127.0.0.1:'+server.address().port;
  const page=await browser.newPage({viewport:{width:390,height:844}});page.setDefaultTimeout(10000);const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('https://**/*',r=>r.abort());
  await page.clock.setFixedTime(new Date('2026-10-26T11:00:00Z'));
  await page.goto(origin+'/parking-guide-user/');
  await page.locator('[data-facility-id="target_022"]').click();
  assert.equal(await page.locator('.destination-card').count(),7);
  await page.locator('[data-destination-id="uniqlo"]').click();
  assert.equal(await page.evaluate(()=>state.selectedDestination.buildingId),'uniqlo_okayama_okakita');
  assert.equal(await page.locator('[data-destination-id="uniqlo"]').getAttribute('aria-pressed'),'true');
  await page.evaluate(()=>{
   const f=state.selectedFacility;
   const destinations=structuredClone(f.destinations);destinations.find(d=>d.id==='uniqlo').operations={weeklyHours:{'1':[['09:00','21:00']]},hoursLabel:'09:00–21:00'};
   window.PARKING_LAYOUTS={...window.PARKING_LAYOUTS,[f.id]:{facilityId:f.id,facilityIdentityKey:getFacilityIdentityKeyForUser(f),objects:[],destinations}};
   updateDestinationPanel();saveSelectedDestination();
  });
  assert.equal(await page.evaluate(()=>getOperatingStatus().closingSoon),true);
  assert.match(await page.evaluate(()=>getCurrentGuidanceMessage('en-US')),/closes within one hour/);
  await page.clock.setFixedTime(new Date('2026-10-25T23:00:00Z'));
  assert.equal(await page.evaluate(()=>getOperatingStatus().preOpening),true);
  await page.clock.setFixedTime(new Date('2026-10-25T22:59:00Z'));
  assert.equal(await page.evaluate(()=>getOperatingStatus().closed),true);
  assert.equal(await page.evaluate(()=>prepareSpaces(state.selectedFacility).spaces.length),0);
  await page.screenshot({path:'/tmp/parking-compound-mobile.png',fullPage:true});
  const admin=await browser.newPage({viewport:{width:1440,height:1000}});admin.setDefaultTimeout(10000);admin.on('pageerror',e=>errors.push(e.message));await admin.route('https://**/*',r=>r.abort());await admin.goto(origin+'/parking-guide-admin/');
  await admin.locator('#prefecture-select').selectOption('岡山県');await admin.locator('#facility-select').selectOption('target_022');
  await admin.getByRole('button',{name:'施設内の店舗を管理',exact:true}).click();
  const first=admin.locator('#tenant-rows fieldset').first();await first.getByLabel('店舗名',{exact:true}).fill('店舗名の変更テスト');
  await admin.locator('#tenant-save').click();
  assert.equal(await admin.evaluate(()=>getCurrentLayout().destinations[0].id),'lamu');
  assert.equal(await admin.evaluate(()=>getCurrentLayout().destinations[0].name),'店舗名の変更テスト');
  await admin.locator('#tenant-close').click();
  await admin.getByRole('button',{name:'営業時間・休業・共用区画',exact:true}).click();
  await admin.locator('#operation-scope').selectOption('uniqlo');await admin.locator('#facility-hours-label').fill('10:00–20:00');await admin.locator('#save-facility-operation').click();
  assert.equal(await admin.evaluate(()=>getCurrentLayout().destinations.find(d=>d.id==='uniqlo').operations.hoursLabel),'10:00–20:00');
  assert.equal(await admin.evaluate(()=>getCurrentLayout().operations?.hoursLabel||''),'');
  await admin.locator('#close-facility-editor').click();
  // Transferred data uses the same saved format in the user application.
  const saved=await admin.evaluate(()=>structuredClone(getCurrentLayout()));
  await page.evaluate(layout=>{window.PARKING_LAYOUTS={...window.PARKING_LAYOUTS,[layout.facilityId]:layout};updateDestinationPanel();},saved);
  assert.ok((await page.locator('.destination-card').first().textContent()).includes('店舗名の変更テスト'));
  assert.deepEqual(errors,[]);
  console.log('PASS: 7 tenant cards, stable building IDs, opening/closing boundaries, per-tenant hours, admin/user saved data round-trip');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
