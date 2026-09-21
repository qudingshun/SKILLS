#!/usr/bin/env node
/**
 * OpenClaw 技能入口 — SCM 回货计划导入 & 发放
 *
 * 使用方式:
 *   node run.js --material "70C012345" --qty "5" --remarks "售后配件"
 *   node run.js --data "70C11099 2, ABC 3 紧急补货"
 */
const { execSync } = require("child_process");
const path = require("path");

const fs = require("fs");
const SCRIPT_DIR = __dirname;
const PYTHON_SCRIPT = path.join(SCRIPT_DIR, "huihuo_scm.py");
// 固定使用共享虚拟环境 E:\SKILLS\.venv（依赖完整：playwright/ddddocr/cryptography 等）
const VENV_PYTHON = "E:\\SKILLS\\.venv\\Scripts\\python.exe";

function main() {
  const args = process.argv.slice(2);

  // Help
  if (args.includes("--help") || args.includes("-h")) {
    console.log(`
SCM 回货计划导入 & 发放 v2.2

用法:
  node run.js --material <料号> --qty <数量> [--date <日期>] [--remarks <备注>] [--visible]
  node run.js --data "<料号1> <数量1> [日期1] [备注1], <料号2> <数量2> [日期2] [备注2]" [--visible]

示例:
  node run.js --material 70C012345 --qty 5
  node run.js --material 70C012345 --qty 5 --remarks 售后配件
  node run.js --material 70C012345 --qty 5 --date 2026-06-30
  node run.js --material 70C012345 --qty 5 --date 2026-06-30 --remarks 紧急补货
  node run.js --data "70C11099 2 售后配件, ABC 3"
  node run.js --data "70C11099 2 2026-06-30, ABC 3"
  node run.js --data "70C11099 2 2026-06-30 紧急补货, ABC 3"
  node run.js --visible --material 70C012345 --qty 5
    `);
    return;
  }

  // Parse --material + --qty + [--date] + [--remarks] into --data format
  let dataArg = null;
  const dataIdx = args.indexOf("--data");
  if (dataIdx !== -1 && dataIdx + 1 < args.length) {
    dataArg = args[dataIdx + 1];
    // 如果同时提供了 --date / --remarks，合并到每组数据中
    const dateIdx = args.indexOf("--date");
    const remIdx = args.indexOf("--remarks");
    const dt = dateIdx !== -1 && dateIdx + 1 < args.length ? args[dateIdx + 1] : "";
    const rem = remIdx !== -1 && remIdx + 1 < args.length ? args[remIdx + 1] : "";
    if (dt || rem) {
      const groups = dataArg.split(/,/);
      dataArg = groups.map(g => {
        g = g.trim();
        if (!g) return g;
        const parts = g.split(/\s+/);
        // 日期：插入到第3位（若尚未有日期）
        if (dt) {
          const hasDate = parts.length >= 3 && /^\d{4}-\d{1,2}-\d{1,2}$/.test(parts[2]);
          if (!hasDate) {
            parts.splice(2, 0, dt);
          }
        }
        // 备注：追加到末尾（若尚未有备注）
        if (rem) {
          const hasRemark = parts.length >= 4 || (parts.length >= 3 && !/^\d{4}-\d{1,2}-\d{1,2}$/.test(parts[2]));
          if (!hasRemark) {
            parts.push(rem);
          }
        }
        return parts.join(" ");
      }).join(", ");
    }
  } else {
    const matIdx = args.indexOf("--material");
    const qtyIdx = args.indexOf("--qty");
    const dateIdx = args.indexOf("--date");
    const remIdx = args.indexOf("--remarks");
    if (matIdx !== -1 && qtyIdx !== -1) {
      const mat = matIdx + 1 < args.length ? args[matIdx + 1] : "";
      const qty = qtyIdx + 1 < args.length ? args[qtyIdx + 1] : "";
      const dt = dateIdx !== -1 && dateIdx + 1 < args.length ? args[dateIdx + 1] : "";
      const rem = remIdx !== -1 && remIdx + 1 < args.length ? args[remIdx + 1] : "";
      if (dt && rem) {
        dataArg = `${mat} ${qty} ${dt} ${rem}`;
      } else if (dt) {
        dataArg = `${mat} ${qty} ${dt}`;
      } else if (rem) {
        dataArg = `${mat} ${qty} ${rem}`;
      } else {
        dataArg = `${mat} ${qty}`;
      }
    }
  }

  if (!dataArg) {
    console.error("[ERR] 请提供料号和数量。使用 --help 查看帮助");
    process.exit(1);
  }

  if (!fs.existsSync(VENV_PYTHON)) {
    console.error(`[ERR] 找不到共享虚拟环境: ${VENV_PYTHON}`);
    console.error(`      请确认 E:\\SKILLS\\.venv 存在，或运行: py scripts/install_deps.py`);
    process.exit(1);
  }

  console.log(`\n=== SCM 回货计划导入 & 发放 v2.2 ===`);
  const visibleMode = args.includes("--visible");
  console.log(`数据: ${dataArg}`);
  console.log(`模式: ${visibleMode ? "可见" : "无头"}`);
  console.log(`Python: ${VENV_PYTHON}`);
  console.log(`Python 脚本: ${PYTHON_SCRIPT}\n`);

  const visibleArg = visibleMode ? " --visible" : "";

  try {
    const result = execSync(
      `"${VENV_PYTHON}" "${PYTHON_SCRIPT}" --data "${dataArg}"${visibleArg}`,
      {
        cwd: SCRIPT_DIR,
        stdio: "inherit",
        timeout: 600000, // 10 min timeout for the whole workflow
        env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
      }
    );
    console.log("\n[OK] 回货流程执行完毕");
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
