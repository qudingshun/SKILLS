#!/usr/bin/env node
/**
 * OpenClaw 技能入口 — Whirlpool China 系统数据查询与展示工具
 *
 * 使用方式:
 *   node run.js --material 70C012345                       // 帆软 + SCM 全量
 *   node run.js --material 70C012345 --module fanruan      // 只查帆软库存报表
 *   node run.js --material 70C012345 --module scm          // 只查 SCM
 *   node run.js --material 70C012345 --org M03 --bin A01-01 // 带组织/货位
 *   node run.js --headless --material 70C012345            // 无头模式
 *   node run.js --help                                     // 查看帮助
 */
const { execSync } = require("child_process");
const path = require("path");

const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "system_data_query.py");
const VENV_PYTHON = path.resolve(SCRIPT_DIR, "..", "..", ".venv", "Scripts", "python.exe");

function main() {
  const args = process.argv.slice(2);

  // Help
  if (args.includes("--help") || args.includes("-h")) {
    console.log(`
Whirlpool China 系统数据查询与展示工具 V1.0

用法:
  node run.js --material <料号>                      帆软 + SCM 全量查询
  node run.js --material <料号> --module fanruan     只查帆软库存报表
  node run.js --material <料号> --module scm         只查 SCM
  node run.js --material <料号> --org <组织> --bin <货位>   带组织/货位
  node run.js --headless --material <料号>           无头模式

选项:
  --material <料号>              必填，要查询的物料编码
  --module <fanruan|scm|all>     指定只运行某个模块（默认 all）
  --org <组织/工厂代码>          可选，帆软作为工厂、SCM 作为组织覆盖
  --bin, --location <货位>       可选，仅帆软库存报表使用
  --headless                     无头模式（不显示浏览器窗口）
  --help, -h                     显示帮助信息

首次运行:
  先运行 node run.js 执行查询（首次需配置加密密码时运行 secure_config.py）
    `);
    return;
  }

  const getOpt = (name) => {
    const i = args.indexOf(name);
    return i !== -1 && i + 1 < args.length ? args[i + 1] : null;
  };

  const material = getOpt("--material");
  if (!material) {
    console.error("[ERR] 必须提供 --material <料号>");
    process.exit(1);
  }
  const org = getOpt("--org");
  const bin = getOpt("--bin") || getOpt("--location");
  const moduleArg = getOpt("--module");
  const headless = args.includes("--headless");

  let pythonArgs = `--material "${material}"`;
  if (org) pythonArgs += ` --org "${org}"`;
  if (bin) pythonArgs += ` --bin "${bin}"`;
  if (moduleArg) {
    const valid = ["fanruan", "scm", "all"];
    if (!valid.includes(moduleArg)) {
      console.error(`[ERR] 无效模块: ${moduleArg}，可选: fanruan, scm, all`);
      process.exit(1);
    }
    pythonArgs += ` --module ${moduleArg}`;
  }

  const moduleLabel = moduleArg ? moduleArg.toUpperCase() : "帆软 + SCM";
  console.log(`\n=== Whirlpool China 系统数据查询与展示工具 V1.0 ===`);
  console.log(`料号: ${material}`);
  if (org) console.log(`组织: ${org}`);
  if (bin) console.log(`货位: ${bin}`);
  console.log(`执行模块: ${moduleLabel}`);
  console.log(`Python 脚本: ${PYTHON_SCRIPT}`);
  console.log(`\n`);

  const env = { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" };
  if (headless) env.OPENCLAW_HEADLESS = "1";

  try {
    const cmd = `"${VENV_PYTHON}" "${PYTHON_SCRIPT}" ${pythonArgs}`;
    execSync(cmd, {
      cwd: SCRIPT_DIR,
      stdio: "inherit",
      timeout: 1200000, // 20 min
      env,
    });
    console.log("\n[OK] 查询执行完毕");
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
