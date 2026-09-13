#!/usr/bin/env python3
"""
SCM 回货计划导入 & 发放 — OpenClaw 技能入口

默认使用可见浏览器模式（有头），OCR 自动识别验证码。
支持 --headless 无头模式。

用法:
  # 单行
  python openclaw_skill.py --material 70C012345 --qty 5
  python openclaw_skill.py --material 70C012345 --qty 5 --remark "售后配件"
  python openclaw_skill.py --material 70C012345 --qty 5 --date 2026-06-30
  python openclaw_skill.py --material 70C012345 --qty 5 --date 2026-06-30 --remark "售后配件"
  python openclaw_skill.py --headless --material 70C012345 --qty 5

  # 多行（逗号分隔）
  python openclaw_skill.py --data "70C11099 2 售后配件, 70A01234 3"
  python openclaw_skill.py --headless --data "70C11099 2 售后配件, 70A01234 3"
"""
import argparse
import subprocess
import sys
import os

_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
_RUN_JS = os.path.join(_SCRIPTS_DIR, "run.js")


def _build_data_arg(args) -> str:
    parts = [args.material, args.qty]
    if args.date:
        parts.append(args.date)
    if args.remark:
        parts.append(args.remark)
    return " ".join(parts)


def _check_deps():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("[ERR] 需要 Node.js")
        sys.exit(1)
    if not os.path.exists(_RUN_JS):
        print(f"[ERR] 找不到 {_RUN_JS}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="SCM 回货计划导入 & 发放 v2.2")
    parser.add_argument("--material", help="料号")
    parser.add_argument("--qty", help="数量")
    parser.add_argument("--date", default="", help="日期 YYYY-MM-DD（可选，默认当月最后一天）")
    parser.add_argument("--remark", default="", help="备注（可选）")
    parser.add_argument("--data", help="多行数据，格式: '料号1 数量1 备注1, 料号2 数量2'")
    parser.add_argument("--headless", action="store_true", help="无头模式（不显示浏览器窗口）")
    args = parser.parse_args()

    if args.data:
        data_arg = args.data
    elif args.material and args.qty:
        data_arg = _build_data_arg(args)
    else:
        parser.print_help()
        print("\n请提供 --material + --qty，或直接使用 --data")
        sys.exit(1)

    _check_deps()

    headless_mode = args.headless
    print(f"\n=== SCM 回货计划导入 & 发放 v2.2 ===")
    print(f"数据: {data_arg}")
    print(f"模式: {'无头' if headless_mode else '可见'}")
    print()

    # 构建命令行参数
    cmd = ["node", _RUN_JS, "--data", data_arg]
    if headless_mode:
        cmd.append("--headless")

    try:
        result = subprocess.run(
            cmd,
            cwd=_SCRIPTS_DIR,
            timeout=600,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
        if result.returncode == 0:
            print("\n[OK] 回货流程执行完毕")
        else:
            print(f"\n[FAIL] 回货流程异常退出 (code {result.returncode})")
            sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        print("\n[FAIL] 回货流程超时 (10分钟)")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 执行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
