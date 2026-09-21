#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WHP-scm-received-inbound 一键依赖安装脚本
========================================

自动安装 WHP-scm-received-inbound 技能所需的全部第三方 Python 包，
并初始化 Playwright 的 Edge 浏览器驱动。

用法（在技能目录下执行）：
    py scripts/install_deps.py

也可加 --no-browser 跳过 Edge 浏览器驱动的下载（系统已装 Edge 时可省）。

说明：
- 系统使用 `py` 命令（不是 `python`），本脚本内部也调用 `py -m pip`。
- 完整依赖 7 个：cryptography / playwright / urllib3 / pandas / openpyxl / ddddocr / lxml
- 另需系统已安装 Microsoft Edge（脚本仅负责 playwright 的 msedge 驱动初始化）
"""

import subprocess
import sys


# 技能实际 import 的第三方包（与 requirements.txt 保持一致）
REQUIRED_PACKAGES = [
    "cryptography",
    "playwright",
    "urllib3",
    "pandas",
    "openpyxl",
    "ddddocr",
    "lxml",
]


def run(cmd):
    """执行命令并打印输出，返回退出码。"""
    print(f"\n$ {' '.join(cmd)}")
    try:
        proc = subprocess.run(cmd, check=False)
        return proc.returncode
    except FileNotFoundError as e:
        print(f"  [错误] 命令不存在：{e}")
        return 127


def main():
    # 用当前解释器对应的 py 启动器；若不在 PATH 则退回 sys.executable
    py = "py"
    try:
        subprocess.run([py, "--version"], check=True,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        py = sys.executable
        print(f"  [提示] 未找到 py 启动器，改用 {py}")

    # 1) 安装所有 Python 包
    print("=" * 60)
    print("  安装 Python 依赖包")
    print("=" * 60)
    pip_cmd = [py, "-m", "pip", "install", "--upgrade"]
    rc = run(pip_cmd + REQUIRED_PACKAGES)
    if rc != 0:
        print(f"\n  [失败] pip install 返回非零退出码 {rc}，请检查网络/源。")
        sys.exit(rc)

    # 2) 验证全部可导入
    print("\n" + "=" * 60)
    print("  验证依赖可导入")
    print("=" * 60)
    verify = [py, "-c",
              "import " + ", ".join(REQUIRED_PACKAGES) + "; print('all OK')"]
    if run(verify) != 0:
        print("  [失败] 部分依赖导入失败，请查看上方报错。")
        sys.exit(1)

    # 3) 初始化 Edge 浏览器驱动（除非 --no-browser）
    if "--no-browser" not in sys.argv:
        print("\n" + "=" * 60)
        print("  初始化 Playwright Edge 驱动")
        print("=" * 60)
        if run([py, "-m", "playwright", "install", "msedge"]) != 0:
            print("  [警告] Edge 驱动初始化失败，请确认系统已安装 Microsoft Edge。")
    else:
        print("\n  [跳过] 已指定 --no-browser，未初始化 Edge 驱动。")

    print("\n" + "=" * 60)
    print("  [完成] WHP-scm-received-inbound 依赖安装完毕")
    print("=" * 60)


if __name__ == "__main__":
    main()
