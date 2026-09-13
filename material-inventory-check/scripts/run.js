#!/usr/bin/env node
/**
 * material-inventory-check 入口 — 薄打包代理
 * 委托给 E:\SKILLS 共享 .venv 执行 scripts/query.py
 *
 * 用法:
 *   node run.js <料号>
 */
const { execSync } = require("child_process");
const path = require("path");

const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "query.py");
const VENV_PYTHON = path.resolve(SCRIPT_DIR, "..", "..", ".venv", "Scripts", "python.exe");

function main() {
  const args = process.argv.slice(2);

  if (args.includes("--help") || args.includes("-h")) {
    console.log(`查料号工具\n\n用法:\n  node run.js <料号>`);
    return;
  }

  const material = args.join(" ");
  if (!material) {
    console.error("[ERR] 请提供料号");
    process.exit(1);
  }

  try {
    execSync(`"${VENV_PYTHON}" "${PYTHON_SCRIPT}" "${material}"`, {
      cwd: SCRIPT_DIR,
      stdio: "inherit",
      timeout: 120000,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    });
    process.exit(0);
  } catch (err) {
    process.exit(err.status || 1);
  }
}

main();