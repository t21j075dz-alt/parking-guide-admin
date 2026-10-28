"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const root=path.resolve(__dirname,"..");
const read=name=>fs.readFileSync(path.join(root,name),"utf8");
const html=read("index.html");
const script=read("admin-workspace-v2.js");
const styles=read("admin-workspace-v2.css");

test("新レイアウトを既存スクリプトの後、CSSを最終スタイルとして読み込む",()=>{
 assert.ok(html.indexOf("admin-workspace-v2.js")>html.indexOf("camera-view.js"));
 assert.ok(html.indexOf("admin-workspace-v2.css")>html.indexOf("experience.css"));
 assert.doesNotThrow(()=>new (require("node:vm").Script)(script));
});
test("施設切替と保存・取り消しの既存IDを維持する",()=>{
 for(const id of ["facility-search","prefecture-select","facility-select","save-button","undo-button","redo-button","canvas-scroll","map-canvas","add-parking-space-button","new-parking-space-type","object-form"]){
  assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(script,/layout\.before\(facilityStrip\)/);
 assert.match(script,/header\.append\(statusRow\)/);
});
test("左右パネルの状態はUI設定だけに保存し、編集データを書き換えない",()=>{
 assert.match(script,/parking-admin-workspace-v1/);
 assert.match(script,/body\.dataset\.adminToolsOpen/);
 assert.match(script,/body\.dataset\.adminSettingsOpen/);
 assert.match(script,/body\.dataset\.adminFocus/);
 assert.match(script,/desktop\[side\]=!desktop\[side\]/);
 assert.doesNotMatch(script,/state\.layouts\s*=|saveLocal\(|getCurrentLayout\(\)\.objects\s*=/);
});
test("モバイルの横はみ出しを防ぎ、閉じたパネルを慣性操作対象にしない",()=>{
 assert.match(styles,/body\.admin-layout-ready\s*\{[^}]*min-width:320px/s);
 assert.match(styles,/@media\(max-width:900px\)/);
 assert.match(styles,/\.admin-sidebar-backdrop/);
 assert.match(script,/tools\.inert=!showTools/);
 assert.match(script,/inspector\.inert=!showSettings/);
 assert.match(script,/event\.key!=="Escape"/);
 assert.match(script,/aria-expanded/);
});
test("マップ上の追加・編集モード・ズーム・詳細設定の既存操作を保持する",()=>{
 for(const id of ["admin-quick-space-type","admin-quick-space-add","new-parking-space-type","add-parking-space-button","rotate-left-button","rotate-right-button"]){
  assert.ok(script.includes(id),id);
 }
 assert.match(script,/originalAdd\.click\(\)/);
 assert.match(script,/advanced\.append\(existingAdvanced\)/);
 assert.match(script,/collapseSection\("\.parking-marking-settings"/);
 assert.match(script,/collapseSection\("\.adjacent-generator"/);
 assert.match(script,/attributeFilter:\["lang"\]/);
});
