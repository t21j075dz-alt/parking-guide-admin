"use strict";
// 録画実験の起動経路を静的に守る。実カメラやクラウドへは接続しない。
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vision=path.join(__dirname,"..","parking-vision");
const read=name=>fs.readFileSync(path.join(vision,name),"utf8");

test("Nikko all-app launcher only offers exports belonging to the recorded camera",()=>{
  const ps=read("start_nikko_all_apps.ps1");
  const cmd=read("道の駅日光_全アプリ反映.cmd");
  assert.match(ps,/facility_id -ne "nikko-test-001"/);
  assert.match(ps,/camera_id -ne "nikko-recording-01"/);
  assert.match(ps,/Get-ChildItem .*"camera-map-alignment-\*\.json"/);
  assert.match(ps,/Read-Host "反映するJSON番号/);
  assert.match(ps,/start_nikko_video\.ps1/);
  assert.match(ps,/-Alignment \$Alignment -VideoDirectory \$VideoDirectory -Share/);
  assert.match(cmd,/start_nikko_all_apps\.ps1/);
  assert.match(cmd,/powershell\.exe -NoProfile -ExecutionPolicy Bypass/);
});

test("changed alignment is imported even if the old YOLO config is already ready",()=>{
  const ps=read("start_nikko_video.ps1");
  assert.match(ps,/if \(-not \(Test-Ready\) -or -not \[string\]::IsNullOrWhiteSpace\(\$Alignment\)\)/);
  assert.match(ps,/& \$python @arguments\n\s+if \(\$LASTEXITCODE -ne 0\)/);
  assert.match(ps,/Read-Host "動画の3場面を確認して録画設定へ取り込む場合だけ「取込」と入力"/);
  assert.match(ps,/& \$python @arguments "--apply"/);
  assert.ok(ps.indexOf('& $python @arguments "--apply"')<
    ps.indexOf('& $python @checkArgs\nif ($LASTEXITCODE -ne 0)'));
});

test("recorded replay remains isolated, looped and requires explicit publication",()=>{
  const ps=read("start_nikko_video.ps1");
  const cmd=read("道の駅日光_全アプリ反映.cmd");
  assert.match(ps,/config_nikko_video_demo\.json/);
  assert.match(ps,/config\.json.*ありません/);
  assert.match(ps,/--loop-video/);
  assert.match(ps,/Read-Host "共有する場合だけ「録画共有」と入力"/);
  assert.match(ps,/Read-Host "静止画も公開する場合だけ「写真も共有」と入力"/);
  assert.match(ps,/--demo-publish/);
  assert.match(ps,/--share-recorded-stills/);
  assert.doesNotMatch(cmd,/service_role|secret_key/);
});
