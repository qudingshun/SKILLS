#!/usr/bin/env python3
"""
系统数据查询与展示 — OpenClaw 技能入口

默认使用可见浏览器模式（有头），OCR 自动识别验证码。
支持 --headless 无头模式。

用法:
  python openclaw_skill.py --material 70C012345
  python openclaw_skill.py --material 70C012345 --module fanruan
  python openclaw_skill.py --material 70C012345 --module scm
  python openclaw_skill.py --material 70C012345 --org M03 --bin A01-01
  python openclaw_skill.py --headless --material 70C012345
"""
import argparse
import subprocess
import sys
import os

_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
_RUN_JS = os.path.join(_SCRIPTS_DIR, "run.js")


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
    parser = argparse.ArgumentParser(description="系统数据查询与展示 v1.0")
    parser.add_argument("--material", required=True, help="料号（必填）")
    parser.add_argument("--org", default=None, help="组织/工厂代码（可选）")
    parser.add_argument("--bin", "--location", dest="bin", default=None,
                        help="货位（可选，仅帆软库存报表使用）")
    parser.add_argument("--module", choices=("fanruan", "scm", "all"), default="all",
                        help="查询模块，默认 all")
    parser.add_argument("--headless", action="store_true", help="无头模式（不显示浏览器窗口）")
    args = parser.parse_args()

    _check_deps()

    cmd = ["node", _RUN_JS, "--material", args.material]
    if args.org:
        cmd += ["--org", args.org]
    if args.bin:
        cmd += ["--bin", args.bin]
    if args.module != "all":
        cmd += ["--module", args.module]
    if args.headless:
        cmd.append("--headless")

    print(f"\n=== 系统数据查询与展示 v1.0 ===")
    print(f"料号: {args.material}" + (f"  组织: {args.org}" if args.org else "") +
          (f"  货位: {args.bin}" if args.bin else ""))
    print(f"模块: {args.module.upper()}  模式: {'无头' if args.headless else '可见'}")
    print()

    try:
        result = subprocess.run(
            cmd,
            cwd=_SCRIPTS_DIR,
            timeout=1200,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"},
        )
        if result.returncode == 0:
            print("\n[OK] 查询执行完毕")
        else:
            print(f"\n[FAIL] 查询异常退出 (code {result.returncode})")
            sys.exit(result.returncode)
    except subprocess.TimeoutExpired:
        print("\n[FAIL] 查询超时 (20分钟)")
        sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] 执行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
