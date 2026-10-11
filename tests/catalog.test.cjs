const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
test('管理JSとJSONは同じ施設マスターで、福岡県100店舗のID・座標を保持する',()=>{
  const c=vm.createContext({window:{}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../facility-catalog.js'),'utf8'),c);
  const js=JSON.parse(JSON.stringify(c.window.ADMIN_FACILITY_CATALOG));
  const json=JSON.parse(fs.readFileSync(path.join(__dirname,'../facility-catalog.json'),'utf8'));
  assert.deepEqual(js,json);
  assert.equal(js.facilities.length,211);
  assert.equal(new Set(js.facilities.map(f=>f.id)).size,211);
  const f=js.facilities.filter(f=>f.prefecture==='福岡県');
  assert.equal(f.length,100);
  for(const r of Object.keys(js.metadata.fukuokaRegionCounts))assert.equal(f.filter(f=>f.region===r).length,25);
  assert.ok(f.every(f=>Number.isFinite(f.latitude)&&Number.isFinite(f.longitude)&&f.layoutId===f.id));
});
