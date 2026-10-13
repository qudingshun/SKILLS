#!/usr/bin/env node
/**
 * OpenClaw 技能入口 - Whirlpool China 统一报表下载工具
 *
 * 使用方式:
 *   node run.js                           // 全量下载:SCM -> OA -> 帆软
 *   node run.js --module scm              // 只下载 SCM 报表
 *   node run.js --module oa               // 只下载 OA 计划
 *   node run.js --module fanruan          // 只下载帆软报表
 *   node run.js --help                    // 查看帮助
 */
const { execSync } = require("child_process");
const path = require("path");

const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "unified_report_downloader.py");
const VENV_PYTHON = path.resolve(SCRIPT_DIR, "..", "..", ".venv", "Scripts", "python.exe");

function main() {
  const args = process.argv.slice(2);

  // Help
  if (args.includes("--help") || args.includes("-h")) {
    console.log(`
Whirlpool China 统一报表下载工具 V2.2

用法:
  node run.js                           全量下载:SCM -> OA -> 帆软
  node run.js --module scm              只下载 SCM 报表(5个任务)
  node run.js --module oa               只下载 OA 生产计划
  node run.js --module fanruan          只下载帆软报表(4个任务)

选项:
  --module <scm|oa|fanruan>   指定只运行某个模块(默认全量)
  --help, -h                  显示帮助信息

首次运行:
  先运行 E:/SKILLS/.venv/Scripts/python.exe scripts/download_secure_config.py 设置加密密码
  再运行 node run.js 执行下载
    `);
    return;
  }

  // Parse --module
  const moduleIdx = args.indexOf("--module");
  const moduleArg = moduleIdx !== -1 && moduleIdx + 1 < args.length ? args[moduleIdx + 1] : null;

  // Parse --visible (可见模式,默认关闭;浏览器默认无头,调试/手动输验证码时加 --visible)
  const visible = args.includes("--visible");

  // Build Python command
  let pythonArgs = "";
  if (moduleArg) {
    const validModules = ["scm", "oa", "fanruan"];
    if (!validModules.includes(moduleArg)) {
      console.error(`[ERR] 无效模块: ${moduleArg},可选: scm, oa, fanruan`);
      process.exit(1);
    }
    pythonArgs = `--module ${moduleArg}`;
  }

  const moduleLabel = moduleArg ? moduleArg.toUpperCase() : "SCM + OA + 帆软";

  console.log(`\n=== Whirlpool China 统一报表下载工具 V2.2 ===`);
  console.log(`执行模块: ${moduleLabel}`);
  console.log(`Python 脚本: ${PYTHON_SCRIPT}`);
  if (pythonArgs) console.log(`参数: ${pythonArgs}`);
  console.log(`\n`);

  try {
    const cmd = pythonArgs
      ? `"${VENV_PYTHON}" "${PYTHON_SCRIPT}" ${pythonArgs}`
      : `"${VENV_PYTHON}" "${PYTHON_SCRIPT}"`;

    const result = execSync(cmd, {
      cwd: SCRIPT_DIR,
      stdio: "inherit",
      timeout: 1200000, // 20 min timeout for full workflow
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1", WP_HEADLESS: visible ? "0" : "1" },
    });
    console.log("\n[OK] 报表下载执行完毕");
    console.log("[LOG] 执行结果已写入 scripts/logs/report_downloader.log");
    process.exit(0);
  } catch (err) {
    if (err.signal === "SIGTERM") {
      console.error("\n[ERR] 脚本被终止");
    } else if (err.killed) {
      console.error("\n[ERR] 脚本超时 (20分钟)");
    } else {
      console.error(`\n[ERR] 脚本异常退出 (code ${err.status || "?"})`);
    }
    process.exit(err.status || 1);
  }
}

main();
