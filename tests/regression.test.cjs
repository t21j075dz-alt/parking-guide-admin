const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const {element,walk}=require('./fake-dom.cjs');

// ブラウザー初期化を除き実際のコードを実行する。通信・保存先はテスト内に限定する。
function app() {
  const nodes = new Map();
  const document = { querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  }, querySelectorAll(){return [];}, createElement:element,createElementNS:(_,tag)=>element(tag) };
  const context = vm.createContext({ document, console, structuredClone, CSS:{escape:String}, setTimeout, clearTimeout, AbortSignal,
    window: { PARKING_REMOTE_CONFIG: { enabled: true, supabaseUrl: 'https://example.test', publishableKey: 'sb_publishable_test' } },
    localStorage: { setItem() {} }, sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    fetch: async () => { throw new Error('Unexpected network request'); },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../map-display.js'), 'utf8'), context);
  const source = fs.readFileSync(process.env.PARKING_TEST_SOURCE || path.join(__dirname, '../admin.js'), 'utf8');
  vm.runInContext(source.split('/* 編集モードは同時に1つだけ有効にする。 */')[0], context);
  const run = (code) => vm.runInContext(code, context);
  run('const renderMapForTest=render; render = () => {};');
  return { run, context, nodes };
}

test('実験地点のGPSはクラウド保存から除外し、管理端末上は維持する', () => {
  const {run}=app();
  run(`state.facilities=[
    {id:'nikko-test-001',requiresLocalCalibration:true},
    {id:'home-test-001',requiresLocalCalibration:true},
    {id:'target_021',requiresLocalCalibration:false}
  ];`);
  for(const id of ['nikko-test-001','home-test-001']){
    const layout={facilityId:id,background:{centerLat:34.7,centerLng:133.9},objects:[]};
    assert.equal(run('layoutForRemoteUpload('+JSON.stringify(layout)+').background'),null);
    assert.equal(layout.background.centerLat,34.7);
  }
  const ordinary={facilityId:'target_021',background:{centerLat:34.7,centerLng:133.9},objects:[]};
  assert.equal(run('layoutForRemoteUpload('+JSON.stringify(ordinary)+').background.centerLat'),34.7);
});

test('再描画しても手動設定した25×50の駐車枠を縮めない', () => {
  const { run } = app();
  run(`state.layouts.a = { facilityId: 'a', objectDefaultsVersion: 11, canvasSizeVersion: 2,
    canvas: { width: 1800, height: 1200 }, objects: [{ uid: 'p', objectType: 'parkingSpace', x: 10, y: 20, width: 25, height: 50 }] };
    ensureLayout('a'); ensureLayout('a');`);
  assert.equal(run('state.layouts.a.objects[0].width'), 25);
  assert.equal(run('state.layouts.a.objects[0].x'), 10);
});

test('バージョンなし旧キャンバスを一度だけ移行する', () => {
  const { run } = app();
  run(`state.layouts.a = { facilityId: 'a', canvas: { width: 1000, height: 700 }, objects: [] }; ensureLayout('a');`);
  assert.equal(run('state.layouts.a.canvas.width'), 1800);
  run(`state.layouts.a.canvas.width = 900; ensureLayout('a');`);
  assert.equal(run('state.layouts.a.canvas.width'), 900);
});

test('旧形式の区画線幅を読み込んでも例外を出さず一度だけ移行する', () => {
  const { run } = app();
  run(`state.layouts.a = { facilityId: 'a', objectDefaultsVersion: 9,
    canvas: { width: 1800, height: 1200, scaleMetersPerPixel: .1 },
    objects: [{ uid: 'p', objectType: 'parkingSpace', x: 10, y: 20, width: 25, height: 50, markingWidth: .4 }] };
    ensureLayout('a'); ensureLayout('a');`);
  assert.equal(run('state.layouts.a.objects[0].markingWidth'), .35);
  assert.equal(run('state.layouts.a.objects[0].width'), 25);
  assert.equal(run('state.layouts.a.objects[0].x'), 10);
});

test('不正なJSONを拒否し、既存の編集を保持する', async () => {
  for (const data of [
    { a: { facilityId: 'b', objects: [] } },
    { a: { facilityId: 'a', objects: [null] } },
    { a: { facilityId: 'a', canvas: 'invalid', objects: [] } },
    { a: { facilityId: 'a', background: { centerLat: null }, objects: [] } },
    { a: { facilityId: 'a', objects: [{ uid: 'p', objectType: 'road', x: 0, y: 0, polygonPoints: [null] }] } },
  ]) {
    const { run, context } = app();
    run(`state.facilityId = 'a'; ensureLayout('a'); state.layouts.a.note = 'keep';`);
    context.file = { text: async () => JSON.stringify(data) };
    await assert.rejects(run('importJson(file)'));
    assert.equal(run('state.layouts.a.note'), 'keep');
  }
});

test('正常なJSONバックアップを復元できる', async () => {
  const { run, context } = app();
  run(`state.facilityId = 'a';`);
  context.file = { text: async () => JSON.stringify({ a: { facilityId: 'a', objects: [] } }) };
  await run('importJson(file)');
  assert.equal(run('state.layouts.a.facilityId'), 'a');
});

test('端末保存失敗を画面に表示する', () => {
  const { run, context, nodes } = app();
  context.localStorage.setItem = () => { throw new Error('QuotaExceededError'); };
  run('saveLocal()');
  assert.match(nodes.get('#local-save-status')?.textContent || '', /保存できません/);
});

test('ログインとクラウド読込の通信失敗を未処理例外にしない', async () => {
  const { run, nodes } = app();
  nodes.get('#cloud-email').value = 'test@example.test';
  nodes.get('#cloud-password').value = 'dummy';
  await run('remoteLogin()');
  assert.match(nodes.get('#cloud-sync-status').textContent, /ログインできません/);
  run(`state.remoteAccessToken = 'test';`);
  await run('loadRemoteLayouts()');
  assert.match(nodes.get('#cloud-sync-status').textContent, /読み込めません/);
});

test('sessionStorageが禁止されていても起動とログアウトができる', () => {
  const { run, context } = app();
  context.sessionStorage.getItem = context.sessionStorage.removeItem = () => { throw new Error('SecurityError'); };
  run('restoreRemoteSession(); remoteLogout();');
  assert.equal(run('state.remoteAccessToken'), null);
});

test('同一施設の保存は順番に送信され、最後に最新編集を保存する', async () => {
  const { run, context } = app();
  const bodies = [];
  let finish;
  context.fetch = async (_url, options) => {
    bodies.push(JSON.parse(options.body));
    if (bodies.length === 1) await new Promise((resolve) => { finish = resolve; });
    return { ok: true };
  };
  run(`state.facilityId = 'a'; ensureLayout('a'); state.remoteAccessToken = 'test'; state.layouts.a.note = 'old';`);
  const first = run("syncLayoutByFacilityId('a')");
  await new Promise(setImmediate);
  run(`state.layouts.a.note = 'new';`);
  const second = run("syncLayoutByFacilityId('a')");
  await new Promise(setImmediate);
  assert.equal(bodies.length, 1);
  finish();
  await Promise.all([first, second]);
  assert.equal(bodies[1].layout_data.note, 'new');
});

test('クラウド読込待ち中の編集を消さない', async () => {
  const { run, context } = app();
  let finish;
  context.fetch = () => new Promise((resolve) => { finish = resolve; });
  run(`state.facilityId = 'a'; ensureLayout('a'); state.remoteAccessToken = 'test';`);
  const pending = run('loadRemoteLayouts()');
  run(`state.layouts.a.note = 'keep'; persistLocalLayouts();`);
  finish({ ok: true, json: async () => [{ facility_id: 'a', layout_data: { facilityId: 'a', objects: [] } }] });
  await pending;
  assert.equal(run('state.layouts.a.note'), 'keep');
});

test('ログイン待ち中にログアウトした場合はセッションを復活させない', async () => {
  const { run, context, nodes } = app();
  let finish;
  context.fetch = () => new Promise((resolve) => { finish = resolve; });
  nodes.get('#cloud-email').value = 'test@example.test';
  nodes.get('#cloud-password').value = 'dummy';
  const pending = run('remoteLogin()');
  run('remoteLogout()');
  finish({ ok: true, json: async () => ({ access_token: 'test' }) });
  await pending;
  assert.equal(run('state.remoteAccessToken'), null);
});

function setLayout(instance,objects){instance.context.objects=objects;instance.run(`state.facilityId='a';state.layouts.a={facilityId:'a',objectDefaultsVersion:11,canvasSizeVersion:2,canvas:{width:1800,height:1200},objects};state.selectedUid=objects[0]?.uid;`);}
test('列内の採番・複製・隣接区画作成はグループを保持し、UIDと番号を重複させない',()=>{const instance=app(),{run,nodes}=instance;setLayout(instance,[{uid:'p',objectType:'parkingSpace',spaceType:'standard',spaceNumber:'001',spaceGroup:'A',spaceGroupKind:'area',x:10,y:10,width:6,height:12},{uid:'q',objectType:'parkingSpace',spaceNumber:'002',spaceGroup:'B',spaceGroupKind:'row',x:100,y:100,width:6,height:12}]);run('duplicateSelected()');assert.equal(run('state.layouts.a.objects[2].spaceNumber'),'002');assert.equal(run('mapDisplay.spaceName(state.layouts.a.objects[2])'),'A区画 2');nodes.get('#adjacent-count').value='2';run("createAdjacentSpaces('right')");const result=JSON.parse(run('JSON.stringify(state.layouts.a.objects)'));const group=result.filter(o=>o.spaceGroup==='A');assert.ok(group.length>=3);assert.equal(new Set(group.map(o=>o.uid)).size,group.length);assert.equal(new Set(group.map(o=>Number(o.spaceNumber))).size,group.length);});
test('番号と列の入力を保存し、カスタム名称を保ち、重複入力では既存データを変えない',()=>{const instance=app(),{run,nodes}=instance;setLayout(instance,[{uid:'p',objectType:'parkingSpace',name:'来客優先',spaceNumber:'001',x:10,y:10,width:25,height:50,spaceType:'standard'},{uid:'q',objectType:'parkingSpace',spaceNumber:'002',spaceGroup:'A',spaceGroupKind:'row',x:100,y:100,width:6,height:12}]);run(`updateSettings=()=>{};elements.name.value='来客優先';elements.x.value='10';elements.y.value='10';elements.width.value='25';elements.height.value='50';elements.spaceType.value='standard';elements.spaceNumber.value='０１';elements.spaceGroup.value='Ａ列';elements.spaceGroupKind.value='row';elements.spaceMarkingStyle.value='full';elements.spaceMarkingColor.value='#fff';elements.spaceMarkingWidth.value='.35';elements.spaceStatus.value='available';updateSelectedFromForm();`);assert.equal(run('mapDisplay.spaceName(state.layouts.a.objects[0])'),'A列 1');assert.equal(run('state.layouts.a.objects[0].name'),'来客優先');const before=run('JSON.stringify(state.layouts.a.objects[0])');run("elements.spaceNumber.value='002';elements.width.value='80';updateSelectedFromForm()");assert.match(nodes.get('#space-number-error').textContent,/重複/);assert.equal(run('JSON.stringify(state.layouts.a.objects[0])'),before);run("elements.spaceNumber.value='abc';updateSelectedFromForm()");assert.match(nodes.get('#space-number-error').textContent,/数字/);});
test('22種類の実際の編集レンダラーで番号・種別・標識を一度だけ描画する',()=>{const instance=app(),{run,nodes}=instance;run(`objects=mapDisplay.types.map((objectType,i)=>({uid:'o'+i,objectType,name:'名称',spaceNumber:'001',spaceGroup:'A',spaceGroupKind:'area',spaceType:'ev',markingStyle:'photoStall',routeNumber:'123',signType:'stop',x:i*30,y:30,width:25,height:50}));`);setLayout(instance,run('objects'));run(`state.selectedUid=null;updateBackgroundControls=()=>{};updateEditModeUi=()=>{};updateGridAppearance=()=>{};renderBackground=()=>{};applyViewScale=()=>{};updateSettings=()=>{};renderMapForTest();`);const canvas=nodes.get('#map-canvas');assert.equal(canvas.children.length,22);const parking=canvas.children.find(n=>n.dataset.objectType==='parkingSpace');assert.equal(walk(parking).filter(n=>n.className==='space-number-mark').length,1);assert.equal(parking.textContent,'EVA区画\n1');assert.ok(!walk(parking).some(n=>n.className==='object-label'));const sign=canvas.children.find(n=>n.dataset.objectType==='roadSign');assert.equal(sign.children.length,1);assert.equal(walk(sign).filter(n=>n.tagName==='text'&&n.textContent==='止まれ').length,1);});
test('リサイズ操作中に文字サイズを即時更新し、建物の手動文字サイズも外形内に制限する',()=>{const instance=app(),{run,nodes}=instance;setLayout(instance,[{uid:'p',objectType:'parkingSpace',spaceNumber:'001',spaceGroup:'A',x:10,y:10,width:6,height:12}]);const node=element();node.dataset.uid='p';nodes.get('#map-canvas').append(node);run(`mapDisplay.applyTypography(elements.canvas.children[0],state.layouts.a.objects[0]);state.resize={pointerId:1,startScrollX:0,startScrollY:0,scale:1,startClientX:0,startClientY:0,rotation:0,direction:'se',width:6,height:12,x:10,y:10};`);const before=Number.parseFloat(node.style['--space-number-size']);run('moveResize({pointerId:1,clientX:20,clientY:40})');assert.ok(Number.parseFloat(node.style['--space-number-size'])>before);assert.ok(run(`getBuildingLabelFontSize({name:'長い名称の建物',width:3,height:3,labelAutoScale:false,labelFontSize:18})`)<3);});
test('JSON保存・復元は列名と区画種別・番号・文字設定を保持する',async()=>{const instance=app(),{run,context}=instance;const item={uid:'p',objectType:'parkingSpace',spaceNumber:'012',spaceGroup:'B',spaceGroupKind:'area',x:10,y:10,width:25,height:50};setLayout(instance,[item]);const backup=run('JSON.stringify(state.layouts)');context.file={text:async()=>backup};await run('importJson(file)');assert.equal(run('mapDisplay.spaceName(state.layouts.a.objects[0])'),'B区画 12');});
test('写真縮尺で普通・軽・車いす・優先枠を実寸生成し、既存図形は変更しない',()=>{
 const {run}=app();run(`state.facilityId='a';ensureLayout('a');state.layouts.a.background={type:'gsi-seamlessphoto',centerLat:34,centerLng:133,zoom:18};initializePhotoScale(state.layouts.a);`);
 for(const type of ['standard','compact','accessible','priority']){run(`addObject('parkingSpace',{spaceType:'${type}'});`);const values=run(`(()=>{const i=getSelectedObject(),p=PARKING_SPACE_PRESETS[i.spaceType],s=getLayoutScale(getCurrentLayout());return [i.width*s,i.height*s,p.widthMeters,p.lengthMeters]})()`);assert.ok(Math.abs(values[0]-values[2])<1e-9);assert.ok(Math.abs(values[1]-values[3])<1e-9);}
 const before=run('JSON.stringify(getCurrentLayout().objects)');run('initializePhotoScale(getCurrentLayout());');assert.equal(run('JSON.stringify(getCurrentLayout().objects)'),before);
});
test('既存レイアウトの手動縮尺は航空写真を表示しても保持する',()=>{const {run}=app();run(`state.facilityId='a';ensureLayout('a');getCurrentLayout().canvas.scaleMetersPerPixel=.1;getCurrentLayout().objects=[{uid:'keep',objectType:'parkingSpace',x:5,y:6,width:25,height:50}];getCurrentLayout().background={centerLat:34,zoom:18};initializePhotoScale(getCurrentLayout());`);assert.equal(run('getLayoutScale(getCurrentLayout())'),.1);assert.equal(run('getCurrentLayout().objects[0].width'),25);});

test('全46区画プリセットを写真縮尺で作成し、大型バスと貨物車の実寸・禁止枠の状態を保つ',()=>{
 const {run}=app();run(`state.facilityId='a';ensureLayout('a');getCurrentLayout().background={type:'gsi-seamlessphoto',centerLat:35,centerLng:135,zoom:18};initializePhotoScale(getCurrentLayout());`);
 const keys=run('Object.keys(PARKING_SPACE_PRESETS)');assert.equal(keys.length,46);
 for(const key of keys){run(`addObject('parkingSpace',{spaceType:${JSON.stringify(key)}})`);const out=JSON.parse(run(`JSON.stringify({item:getSelectedObject(),preset:PARKING_SPACE_PRESETS[getSelectedObject().spaceType],scale:getLayoutScale(getCurrentLayout())})`));assert.ok(Math.abs(out.item.width*out.scale-out.preset.widthMeters)<1e-9,key);assert.ok(Math.abs(out.item.height*out.scale-out.preset.lengthMeters)<1e-9,key);if(!out.preset.guidable)assert.equal(out.item.status,'unavailable',key);}
 assert.equal(run('PARKING_SPACE_PRESETS.bus.widthMeters'),3.3);assert.equal(run('PARKING_SPACE_PRESETS.bus.lengthMeters'),13);assert.equal(run('PARKING_SPACE_PRESETS.smallTruck.lengthMeters'),7.7);
});
