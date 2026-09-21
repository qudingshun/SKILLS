#!/usr/bin/env node
const { execSync } = require("child_process");
const path = require("path");

const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "..", "openclaw_skill.py");
const VENV_PYTHON = path.resolve(SCRIPT_DIR, "..", "..", ".venv", "Scripts", "python.exe");

function main() {
  const args = process.argv.slice(2);

  if (args.includes("--help") || args.includes("-h")) {
    console.log(`BOM核对工具\n\n用法:\n  node run.js                  默认后台运行\n  node run.js --visible        显示Excel窗口\n  node run.js --help           查看帮助`);
    return;
  }

  console.log(`\n=== BOM核对 ===\n`);

  try {
    execSync(`"${VENV_PYTHON}" "${PYTHON_SCRIPT}" ${args.join(" ")}`, {
      cwd: SCRIPT_DIR,
      stdio: "inherit",
      timeout: 300000,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    });
    process.exit(0);
  } catch (err) {
    console.error(`\n[ERR] 脚本异常退出 (code ${err.status || "?"})`);
    process.exit(err.status || 1);
  }
}

main();
