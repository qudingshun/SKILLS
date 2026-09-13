"""
bom-compare 技能入口 — OpenClaw

功能：打开 BOM核对.xlsm，运行核对BOM2宏，读取结果并过滤掉 C 列=无差异 的行。
默认后台运行，不打扰用户已打开的 Excel 实例。
"""

import os
import sys

_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from run_bom_compare import run_bom_compare  # noqa: E402


def main():
    visible = "--visible" in sys.argv
    result = run_bom_compare(visible=visible)

    print("\n=== RESULT ===")
    print("Status: {}".format(result.get("status")))
    if result.get("status") == "success":
        print("Total rows: {}".format(result["total"]))
        print("Headers: {}".format(result["headers"]))
        print()
        for i, row in enumerate(result["rows"][:20], 1):
            print("{:3}. {}".format(i, row))
        if result["total"] > 20:
            print("... and {} more rows".format(result["total"] - 20))
        sys.exit(0)
    else:
        print("Error: {}".format(result.get("message")))
        sys.exit(1)


if __name__ == "__main__":
    main()
