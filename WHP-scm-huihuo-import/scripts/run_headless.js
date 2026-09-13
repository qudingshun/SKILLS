#!/usr/bin/env node
/**
 * SCM 回货 — 无头模式入口
 */
const { execSync } = require("child_process");
const path = require("path");

const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "huihuo_scm_headless.py");

function main() {
  const args = process.argv.slice(2);
  const dataIdx = args.indexOf("--data");
  let dataArg = null;

  if (dataIdx !== -1 && dataIdx + 1 < args.length) {
    dataArg = args[dataIdx + 1];
  } else {
    const matIdx = args.indexOf("--material");
    const qtyIdx = args.indexOf("--qty");
    const remIdx = args.indexOf("--remarks");
    if (matIdx !== -1 && qtyIdx !== -1) {
      const mat = matIdx + 1 < args.length ? args[matIdx + 1] : "";
      const qty = qtyIdx + 1 < args.length ? args[qtyIdx + 1] : "";
      const rem = remIdx !== -1 && remIdx + 1 < args.length ? args[remIdx + 1] : "";
      dataArg = rem ? `${mat} ${qty} ${rem}` : `${mat} ${qty}`;
    }
  }

  if (!dataArg) {
    process.exit(1);
  }

  try {
    execSync(`py "${PYTHON_SCRIPT}" --data "${dataArg}"`,
      cwd: SCRIPT_DIR,
      stdio: "inherit",
      timeout: 600000,
      env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
    });
    process.exit(0);
  } catch (err) {
    process.exit(err.status || 1);
  }
}

main();
