"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { buildRecordingDemo, parseCsvLine } = require("../recording-demo.js");

test("自宅駐車場の録画CSVは過去の状態変化だけを圧縮する", () => {
  const csv = [
    "\uFEFF動画の時刻(秒),駐車枠ID,判定,判定コード,車両検知数,障害物検知数",
    "0.0,space_001,確認できない,unknown,1,0",
    "0.0,space_002,確認できない,unknown,0,0",
    "0.4,space_001,駐車中,occupied,1,0",
    "0.4,space_002,確認できない,unknown,0,0",
    "1.4,space_001,駐車中,occupied,1,0",
    "1.4,space_002,空き,available,0,0",
  ].join("\r\n");
  const payload = buildRecordingDemo(csv);
  assert.equal(payload.facility_id, "home-test-001");
  assert.equal(payload.duration, 1.4);
  assert.deepEqual(payload.spaces, ["space_001", "space_002"]);
  assert.deepEqual(payload.events, [[0,0,0],[0,1,0],[0.4,0,2],[1.4,1,1]]);
  assert.equal(Object.hasOwn(payload, "video"), false);
  assert.equal(Object.hasOwn(payload, "vehicle_id"), false);
});
test("誤ったCSVや施設IDはアプリ連携しない", () => {
  assert.throws(() => buildRecordingDemo("a,b,c\n1,2,3"), /駐車枠の状態/);
  assert.throws(() => buildRecordingDemo("a,b,c\n1,2,3","target_021"), /自宅/);
});
test("CSVの引用符処理が壊れない", () => {
  assert.deepEqual(parseCsvLine('"abc,def","ghi""jkl",x'), ["abc,def",'ghi"jkl',"x"]);
});
