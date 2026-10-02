const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// ブラウザー初期化を除き実際のコードを実行する。通信・保存先はテスト内に限定する。
function app() {
  const nodes = new Map();
  const document = { querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, { value: '', textContent: '' });
    return nodes.get(selector);
  } };
  const context = vm.createContext({ document, console, setTimeout, clearTimeout, AbortSignal,
    window: { PARKING_REMOTE_CONFIG: { enabled: true, supabaseUrl: 'https://example.test', publishableKey: 'sb_publishable_test' } },
    localStorage: { setItem() {} }, sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    fetch: async () => { throw new Error('Unexpected network request'); },
  });
  const source = fs.readFileSync(process.env.PARKING_TEST_SOURCE || path.join(__dirname, '../admin.js'), 'utf8');
  vm.runInContext(source.split('/* 編集モードは同時に1つだけ有効にする。 */')[0], context);
  const run = (code) => vm.runInContext(code, context);
  run('render = () => {};');
  return { run, context, nodes };
}

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
