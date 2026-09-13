#!/usr/bin/env node
const { execSync } = require("child_process");
const path = require("path");

const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "checkin.py");
const VENV_PYTHON = path.resolve(SCRIPT_DIR, "..", ".venv", "Scripts", "python.exe");

function main() {
  const args = process.argv.slice(2);

  if (args.includes("--help") || args.includes("-h")) {
    console.log(`v2free 签到工具\n\n用法:\n  node run.js                  交互式登录并签到\n  node run.js --help           查看帮助`);
    return;
  }

  console.log(`\n=== v2free 签到 ===\n`);

  try {
    execSync(`"${VENV_PYTHON}" "${PYTHON_SCRIPT}" ${args.join(" ")}`, {
      cwd: SCRIPT_DIR,
      stdio: "inherit",
      timeout: 120000,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    });
    console.log("\n[OK] 签到执行完毕");
    process.exit(0);
  } catch (err) {
    console.error(`\n[ERR] 脚本异常退出 (code ${err.status || "?"})`);
    process.exit(err.status || 1);
  }
}

main();
