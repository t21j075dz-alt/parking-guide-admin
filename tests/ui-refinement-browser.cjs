// 外部通信は遮断。端末内のテストデータだけを操作する。
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
(async()=>{
 const root=path.resolve(__dirname,'..');
 const server=http.createServer((req,res)=>{try{let file=path.join(root,new URL(req.url,'http://localhost').pathname);if(fs.statSync(file).isDirectory())file=path.join(file,'index.html');res.setHeader('Content-Type',({'.js':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));}catch{res.writeHead(404).end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 let browser;
 try {
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
  const errors=[];
  for(const width of [390,1440]) {
   const page=await browser.newPage({viewport:{width,height:844}});
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('https://**/*',r=>r.abort());
   await page.goto('http://127.0.0.1:'+server.address().port);

   await page.locator('#admin-tools-toggle').click();
   await page.locator('#admin-tool-search').fill('カメラ');
   assert.equal(await page.locator('#camera-monitor').isVisible(),true);
   await page.locator('#admin-tool-search').fill('存在しない機能XYZ');
   assert.equal(await page.locator('.tool-search [role=status]').isVisible(),true);
   await page.locator('#admin-tool-search').press('Escape');
   assert.equal(await page.locator('#admin-tool-search').inputValue(),'');
   assert.equal(await page.locator('#camera-monitor').isVisible(),true);
   await page.locator('#admin-tools-toggle').click();
   await page.locator('#admin-quick-space-add').click();
   assert.equal(await page.locator('.map-object[data-object-type="parkingSpace"]').count(),1);
   await page.locator('#undo-button').click();
   assert.equal(await page.locator('.map-object[data-object-type="parkingSpace"]').count(),0);
   await page.screenshot({path:'/tmp/admin-refinement-'+width+'.png'});
   await page.locator('[data-action=alignment]').click();
   assert.equal(await page.locator('#camera-map-alignment-dialog').isVisible(),true);
   assert.equal(await page.locator('.alignment-step-number').first().isVisible(),false);
   await page.locator('#alignment-close').click();

   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2),'horizontal overflow');
   await page.close();
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: UI refinement desktop and mobile');
 } finally {if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
