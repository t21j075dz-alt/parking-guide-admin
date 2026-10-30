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
  const context = vm.createContext({window, document:{querySelector:()=>null}});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../voice-speech-readings.js"),"utf8"), context);
  vm.runInContext(source, context);
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


test("an authenticated administrator can retry failed clips without regenerating successful clips", async () => {
  const actions = [];
  const window = { PARKING_SPEECH_READINGS: {} };
  const document = { querySelector() { return null; } };
  const fetch = async (_url, options) => {
    const action = JSON.parse(options.body).action;
    actions.push(action);
    return { ok: true, json: async () => action === "retry-failed"
      ? { requeued: 2 }
      : { totals:{ ready:24,pending:2,processing:0,retry:0,failed:0 },
        byType:{ facility:{ready:24,total:26},tenant:{ready:0,total:0},other:{ready:0,total:0} },total:26 } };
  };
  vm.runInNewContext(source, {window,document,fetch,AbortSignal});
  const api=window.ParkingAdminVoice;
  await api.retryFailed({enabled:true,url:"https://example.test",publishableKey:"publishable"}, "test-token");
  assert.deepEqual(actions,["retry-failed","status"]);
  await api.retryFailed({enabled:true,url:"https://example.test",publishableKey:"publishable"}, null);
  assert.deepEqual(actions,["retry-failed","status"],"unauthorized retry must not send a request");
});


test("registered parking space numbers are queued as reusable spoken components", () => {
  const app=getModule();
  const layout={objects:[
    {objectType:"parkingSpace",spaceNumber:"006",name:"普通車 6"},
    {objectType:"parkingSpace",spaceNumber:"007",spaceGroup:"A",spaceGroupKind:"row"},
    {objectType:"parkingSpace",spaceNumber:"008",spaceNumberReading:"はちばん"},
    {objectType:"building",name:"案内板"},
  ]};
  const audio=app.spaceNames(layout);
  assert.deepEqual(Array.from(audio.map(x=>x.type)),["space","space","space"]);
  assert.deepEqual(Array.from(audio.map(x=>x.text)),[
    "ろく", "えー、れつ なな", "はちばん"
  ]);
  const full=app.itemsForFacility({id:"target_021",name:"マルナカ中井町店"}, layout);
  assert.ok(full.some(x=>x.type==="space"&&x.text==="えー、れつ なな"));
});

test("catalog backfill also includes registered parking spaces in uncatalogued experimental layouts",()=>{
  const app=getModule();
  const list=app.itemsForCatalog([],{
    "experimental":{objects:[{objectType:"parkingSpace",spaceNumber:"012"}]},
  });
  assert.deepEqual(Array.from(list.map(x=>x.text)),["じゅうに"]);
});
