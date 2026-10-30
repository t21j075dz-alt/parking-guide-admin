const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../admin-voice.js"),"utf8");
function getModule() {
  const window = { PARKING_SPEECH_READINGS: {
    target_021: "まるなか なかいちょうてん",
  } };
  vm.runInNewContext(source, {window, document:{querySelector:()=>null}});
  return window.ParkingAdminVoice;
}
test("existing facility names use the configured spoken pronunciation", () => {
  const items=getModule().itemsForCatalog([{id:"target_021",name:"マルナカ中井町店"}],{});
  assert.equal(items.length,1);
  assert.equal(items[0].text,"まるなか なかいちょうてん");
  assert.equal(items[0].type,"facility");
});
test("saving a new tenant generates one facility name and the tenant name", () => {
  const facility={id:"target_021",name:"マルナカ中井町店"};
  const layout={destinations:[{id:"tenant_1",name:"新しい店舗"}]};
  const items=getModule().itemsForFacility(facility,layout);
  assert.deepEqual(Array.from(items.map(x=>x.type)),["facility","tenant"]);
  assert.equal(items[1].text,"新しい店舗");
});
test("a renamed tenant is collected without changing its stable ID", () => {
  const facility={id:"target_021",name:"マルナカ中井町店"};
  const before=getModule().itemsForFacility(facility,{destinations:[{id:"tenant_1",name:"旧店舗名"}]});
  const after=getModule().itemsForFacility(facility,{destinations:[{id:"tenant_1",name:"新店舗名"}]});
  assert.notEqual(before[1].text,after[1].text);
});
test("the catalog removes duplicate names across facilities", () => {
  const items=getModule().itemsForCatalog([
    {id:"target_021",name:"施設A",nameReading:"同じ名前"},
    {id:"target_022",name:"施設B",nameReading:"同じ名前"},
  ],{});
  assert.equal(items.length,1);
});


test("administrator pronunciation overrides written tenant name for TTS generation", () => {
  const list=getModule().itemsForFacility({id:"target_021",name:"マルナカ中井町店"},{
    destinations:[{id:"tenant_new",name:"ABCマーケット",nameReading:"えーびーしー まーけっと"}],
  });
  assert.equal(list[1].text,"えーびーしー まーけっと");
  assert.equal(list[1].type,"tenant");
});
