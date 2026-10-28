// Regression checks use isolated browser storage and block all external requests.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs'),path=require('path'),http=require('http');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const server=http.createServer((req,res)=>{try{let p=path.join(root,new URL(req.url,'http://localhost').pathname);if(fs.statSync(p).isDirectory())p+='/index.html';res.setHeader('Content-Type',({'.js':'text/javascript','.html':'text/html','.css':'text/css'})[path.extname(p)]||'application/json');res.end(fs.readFileSync(p));}catch{res.statusCode=404;res.end();}});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;
 const b=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
 try{
 const page=await b.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.route('https://**/*',r=>r.abort());await page.goto(origin+'/parking-guide-admin/');
 for(const id of ['snap-enabled','parking-snap-strong','site-snap-strong','orthogonal-snap'])assert.equal(await page.locator('#'+id).isChecked(),false);
 // At each scale, sample every pointer step beside another space. No jumps toward it.
 for(const scale of [.5,1,4,16]){
  await page.evaluate(scale=>{getCurrentLayout().objects=[];addObject('parkingSpace');Object.assign(getSelectedObject(),{x:120,y:100,width:25,height:50});addObject('parkingSpace');Object.assign(getSelectedObject(),{x:145,y:100,width:25,height:50});state.selectedUid=getCurrentLayout().objects[0].uid;render();applyViewScale(scale);ParkingEditor.focusSelected();},scale);
  const n=page.locator('.map-object.selected');const box=await n.boundingBox();const vp=await page.locator('#canvas-scroll').boundingBox();
  const x=Math.max(vp.x+20,Math.min(vp.x+vp.width-100,box.x+box.width*.5)),y=Math.max(vp.y+20,Math.min(vp.y+vp.height-70,box.y+box.height*.5));
  const initial=await page.evaluate(()=>({x:getSelectedObject().x,y:getSelectedObject().y}));
  await page.mouse.move(x,y);await page.mouse.down();
  for(let i=1;i<=12;i++){await page.mouse.move(x+i*2,y+i);const current=await page.evaluate(()=>({x:getSelectedObject().x,y:getSelectedObject().y}));assert.ok(Math.abs((current.x-initial.x)*scale-i*2)<.12,`x follows cursor at ${scale}x, step ${i}: ${JSON.stringify({initial,current,x,y,box,vp,gesture:await page.evaluate(()=>({drag:state.drag,resize:state.resize,mode:state.editMode}))})}`);assert.ok(Math.abs((current.y-initial.y)*scale-i)<.12);}
  await page.mouse.up();
 }
 // A vertex follows the cursor, including a rotated building. No orthogonal correction by default.
 for(const rotation of [0,35]){
  await page.evaluate(rotation=>{getCurrentLayout().objects=[];addObject('building');Object.assign(getSelectedObject(),{x:180,y:180,width:90,height:55,rotation});render();applyViewScale(2);setEditMode('reshape');ParkingEditor.focusSelected();},rotation);
  const handle=page.locator('.polygon-handle[data-vertex-index="0"]');const box=await handle.boundingBox();const x=box.x+box.width/2,y=box.y+box.height/2;
  const p0=await page.evaluate(()=>{const o=getSelectedObject();return objectLocalPointToGlobal(o,...Object.values(getPolygonPoints(o)[0]));});
  await page.mouse.move(x,y);await page.mouse.down();
  for(let i=1;i<=10;i++){await page.mouse.move(x+i*2,y+i);const p1=await page.evaluate(()=>{const o=getSelectedObject(),p=getPolygonPoints(o)[0];return objectLocalPointToGlobal(o,p.x,p.y);});assert.ok(Math.abs((p1.x-p0.x)*2-i*2)<.04);assert.ok(Math.abs((p1.y-p0.y)*2-i)<.04);}
  await page.mouse.up();
 }
 // English UI and persisted user-authored translations, without touching coordinates.
 await page.fill('#object-name','店舗');await page.locator('#object-name').blur();await page.fill('#object-name-en','Research Store');await page.locator('#object-name-en').blur();
 await page.evaluate(()=>{addObject('parkingSpace',{spaceType:'bus'});Object.assign(getSelectedObject(),{spaceGroup:'A',spaceNumber:'12',x:260,y:180});addObject('parkingEntrance');Object.assign(getSelectedObject(),{accessType:'exit',x:300,y:230});addObject('pavementMarking',{pavementKind:'slow'});Object.assign(getSelectedObject(),{x:280,y:250});saveLocal();render();ParkingEditor.fitObjects();});
 const original=await page.evaluate(()=>JSON.stringify(getCurrentLayout()));await page.locator('.admin-header-more > summary').click();await page.click('#language-button');assert.equal(await page.locator('html').getAttribute('lang'),'en');assert.equal(await page.locator('#add-parking-space-button').textContent(),'Add parking space');
 assert.ok((await page.locator('#map-canvas').textContent()).includes('BUS\nONLY'));assert.ok((await page.locator('#map-canvas').textContent()).includes('Row A'));assert.ok((await page.locator('#map-canvas').textContent()).includes('Research Store'));assert.ok((await page.locator('#map-canvas').textContent()).includes('EXIT'));assert.ok((await page.locator('#map-canvas').textContent()).includes('SLOW'));
 assert.equal(await page.evaluate(()=>JSON.stringify(getCurrentLayout())),original);
 fs.writeFileSync('/tmp/admin-untranslated.json',JSON.stringify(await page.evaluate(()=>{const out=[],w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);while(w.nextNode()){const n=w.currentNode;if(/[\u3040-\u9fff]/.test(n.textContent)&&!n.parentElement.closest('script,style,#facility-select,#prefecture-select,#facility-address,#facility-results,#map-canvas'))out.push(n.textContent.trim());}return [...new Set(out)];}),null,2));
 await page.screenshot({path:'/tmp/parking-admin-en.png'});
 const layout=await page.evaluate(()=>structuredClone(getCurrentLayout()));await page.reload();assert.equal(await page.locator('html').getAttribute('lang'),'en');await page.locator('.admin-header-more > summary').click();await page.click('#language-button');assert.equal(await page.locator('#add-parking-space-button').textContent(),'駐車枠を追加');
 const user=await b.newPage({viewport:{width:390,height:844}});user.on('pageerror',e=>errors.push(e.message));await user.route('https://**/*',r=>r.abort());await user.goto(origin+'/parking-guide-user/');
 await user.evaluate(layout=>{document.querySelectorAll('.screen').forEach(n=>n.hidden=true);let p=document.querySelector('#parking-map');while(p){p.hidden=false;p.classList?.remove('hidden');p=p.parentElement;}document.querySelector('#launch-screen')?.remove();state.currentLayout=layout;state.currentSpaces=[];state.recommendedSpace=null;state.guideEntrance=null;renderRegisteredLayout(layout,null);},layout);
 await user.evaluate(()=>applyLanguage('en'));
 const text=await user.locator('#parking-map').textContent();for(const expected of ['BUS\nONLY','Row A','Research Store','EXIT','SLOW'])assert.ok(text.includes(expected),expected);
 await user.locator('#parking-map').screenshot({path:'/tmp/parking-user-en.png'});
 await user.evaluate(()=>applyLanguage('ja'));assert.ok((await user.locator('#parking-map').textContent()).includes('バス\n専用'));
 assert.deepEqual(errors,[]);console.log('PASS: cursor tracking at 0.5/1/4/16x; straight/rotated vertices; bilingual maps, names, persistence, unchanged saved geometry, mobile rendering');
 }finally{await b.close();server.close();}
})().catch(e=>{console.error(e);process.exit(1)});
