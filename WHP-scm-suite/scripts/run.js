#!/usr/bin/env node
/**
 * WHP-scm-suite 统一入口
 *
 * 汇集 5 个入口技能的业务代码，按模块路由：
 *   node run.js download  --module scm|oa|fanruan [--headless]
 *   node run.js received  [--headless]
 *   node run.js query     --material <料号> [--module scm|fanruan|all] [--org <org>] [--bin <货位>] [--headless]
 *   node run.js huihuo    --material <料号> --qty <数量> [--date <日期>] [--remarks <备注>] [--headless]
 *   node run.js huihuo    --data "<料号1> <数量1> [日期1] [备注1], ..." [--headless]
 */
const { execSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const SCRIPT_DIR = __dirname;
const SUITE_DIR = path.resolve(SCRIPT_DIR, "..");
const VENV_PYTHON = path.resolve(SUITE_DIR, "..", ".venv", "Scripts", "python.exe");

const MODULES = {
  download: { script: path.join(SCRIPT_DIR, "download", "unified_report_downloader.py") },
  received: { script: path.join(SCRIPT_DIR, "received", "scm_received_inbound.py") },
  query:    { script: path.join(SCRIPT_DIR, "query", "system_data_query.py") },
  huihuo:   { script: path.join(SCRIPT_DIR, "huihuo", "huihuo_scm.py") },
};

function main() {
  const args = process.argv.slice(2);
  const moduleArg = args.shift();

  if (!moduleArg || moduleArg === "--help" || moduleArg === "-h") {
    console.log(`
WHP-scm-suite 统一入口 v1.0

用法:
  node run.js download  --module scm|oa|fanruan [--headless]
  node run.js received  [--headless]
  node run.js query     --material <料号> [--module scm|fanruan|all] [--org <org>] [--bin <货位>] [--headless]
  node run.js huihuo    --material <料号> --qty <数量> [--date <日期>] [--remarks <备注>] [--headless]
  node run.js huihuo    --data "<料号> <数量> [日期] [备注], ..." [--headless]

说明:
  配置文件: runtime_config.json（套件根）
  密码库  : runtime_config/passwords/*.dat（AES-256，SecurePasswordManager）
`);
    return;
  }

  const entry = MODULES[moduleArg];
  if (!entry) {
    console.error(`[ERR] 未知模块: ${moduleArg} （可选: ${Object.keys(MODULES).join(" | ")}）`);
    process.exit(2);
  }
  if (!fs.existsSync(entry.script)) {
    console.error(`[ERR] 找不到脚本: ${entry.script}`);
    process.exit(2);
  }

  const headlessMode = args.includes("--headless");
  const env = {
    ...process.env,
    PYTHONIOENCODING: "utf-8",
    PYTHONUNBUFFERED: "1",
    WP_HEADLESS: headlessMode ? "1" : "0",
  };

  console.log(`\n=== WHP-scm-suite [${moduleArg}] ===`);
  console.log(`脚本: ${entry.script}`);
  console.log(`模式: ${headlessMode ? "无头" : "可见"}\n`);

  try {
    execSync(`"${VENV_PYTHON}" "${entry.script}" ${args.join(" ")}`, {
      cwd: path.dirname(entry.script),
      stdio: "inherit",
      timeout: 600000,
      env,
    });
    console.log(`\n[OK] ${moduleArg} 执行完成`);
    process.exit(0);
  } catch (err) {
    if (err.signal === "SIGTERM") {
      console.error("\n[ERR] 脚本被中止");
    } else if (err.killed) {
      console.error("\n[ERR] 脚本超时 (10分钟)");
    } else {
      console.error(`\n[ERR] 脚本异常退出 (code ${err.status || "?"})`);
    }
    process.exit(err.status || 1);
  }
}

main();