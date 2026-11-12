"use strict";

// Git管理下の全JavaScriptとJSONを確認する。アプリやクラウド処理は実行しない。
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "..");
const files = execFileSync("git", ["ls-files", "-z"], { cwd: root, encoding: "utf8" })
  .split("\0")
  .filter(Boolean);
let checked = 0;
let failed = 0;

for (const file of files) {
  const fullPath = path.join(root, file);
  // 整理中の削除ファイルは、コミット前でも検査対象から除く。
  if (!fs.existsSync(fullPath)) continue;
  try {
    if (/\.(js|cjs)$/.test(file)) {
      execFileSync(process.execPath, ["--check", fullPath], { stdio: "pipe" });
    } else if (/\.(json|webmanifest)$/.test(file)) {
      JSON.parse(fs.readFileSync(fullPath, "utf8"));
    } else {
      continue;
    }
    checked += 1;
  } catch (error) {
    failed += 1;
    console.error(file + ": " + (error.stderr?.toString() || error.message));
  }
}

console.log(`Source check: ${checked} passed, ${failed} failed`);
process.exitCode = failed ? 1 : 0;
