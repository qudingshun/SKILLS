#!/usr/bin/env node
/**
 * 已接收入库 技能入口 — SCM 送货单查询（已接收）导出
 *
 * 使用方式:
 *   node run.js                // 导出当月已接收送货单 → 已入库.xlsx
 *   node run.js --visible      // 可见模式（默认无头）
 *   node run.js --help         // 查看帮助
 */
const { execSync } = require("child_process");
const path = require("path");

const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "scm_received_inbound.py");
const VENV_PYTHON = path.resolve(SCRIPT_DIR, "..", "..", ".venv", "Scripts", "python.exe");

function main() {
  const args = process.argv.slice(2);

  // Help
  if (args.includes("--help") || args.includes("-h")) {
    console.log(`
已接收入库导出工具 V1.3

功能:
  登录 SCM → 送货单查询（已接收）→ 导出「已入库.xlsx」

  查询条件:
    - incept_date_start/incept_date_end 清空后设为 当月1号 ~ 当月最后一天
    - received          = 已接收
    - organization_code = 接收地址（org_code，默认 M03）
    - maxsearchrltcmt   = 99999

用法:
  node run.js                默认无头模式
  node run.js --visible      可见模式（调试/手动输验证码时用）
  node run.js --help         帮助

首次运行:
  密码沿用 WHP-whirlpool-download 技能的 scm_password.dat，
  如需重设可运行: E:/SKILLS/.venv/Scripts/python.exe ../WHP-whirlpool-download/scripts/download_secure_config.py
    `);
    return;
  }

  // Parse --visible
  const visible = args.includes("--visible");

  console.log(`\n=== 已接收入库导出工具 V1.3 ===`);
  console.log(`Python 脚本: ${PYTHON_SCRIPT}`);
  console.log(`\n`);

  try {
    const cmd = `"${VENV_PYTHON}" "${PYTHON_SCRIPT}"${visible ? " --visible" : ""}`;
    const result = execSync(cmd, {
      cwd: SCRIPT_DIR,
      stdio: "inherit",
      timeout: 600000, // 10 min
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1", WP_HEADLESS: visible ? "0" : "1" },
    });
    console.log("\n[OK] 已接收入库导出完毕");
    process.exit(0);
  } catch (err) {
    if (err.signal === "SIGTERM") {
      console.error("\n[ERR] 脚本被终止");
    } else if (err.killed) {
      console.error("\n[ERR] 脚本超时 (10分钟)");
    } else {
      console.error(`\n[ERR] 脚本异常退出 (code ${err.status || "?"})`);
    }
    process.exit(err.status || 1);
  }
}

main();