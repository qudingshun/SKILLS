"""reporting-tools 技能 — 小艺转译版入口

功能：产销存报表 / 跑回货工具

优先级：转译版 → 异常回退 → 外部 PY 脚本
"""
import os
import sys
import subprocess
from datetime import datetime

SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.join(SKILL_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)

VENV_PYTHON = os.path.normpath(os.path.join(SKILL_DIR, "..", ".venv", "Scripts", "python.exe"))

EXTERNAL_SCRIPTS = {
    "run_excel": r"E:\whirlpool-china\run_excel.py",
    "inventory": r"E:\whirlpool-china\inventory_daily_report.py",
}


def run(params: dict = None) -> int:
    trigger = (params or {}).get("trigger", "")
    start = datetime.now()

    task_map = {
        "跑回货工具": "run_excel",
        "产销存报表": "inventory",
    }
    task = task_map.get(trigger)
    if not task:
        for k, v in task_map.items():
            if k in trigger: task = v; break
    if not task:
        print(f"[错误] 未知触发词: {trigger}"); return 1

    ok = _run_task(task)
    elapsed = int((datetime.now() - start).total_seconds())
    print(f"\n  用时: {elapsed}秒  {'成功' if ok else '失败'}")
    return 0 if ok else 1


def _run_task(task_id: str) -> bool:
    """执行单任务：转译 → 回退"""
    try:
        # 优先：转译版
        if task_id == "inventory":
            from transpiled_inventory import run_inventory
            return run_inventory()
        elif task_id == "run_excel":
            from transpiled_run_excel import run_excel
            return run_excel()
    except Exception as e:
        print(f"  [转译] 异常: {e}，回退外部脚本...")

    # 回退：外部 PY 脚本
    ext = EXTERNAL_SCRIPTS.get(task_id)
    if ext and os.path.exists(ext):
        print(f"  [回退] 调用 {os.path.basename(ext)}")
        try:
            r = subprocess.run(
                [VENV_PYTHON, ext],
                cwd=r"E:\whirlpool-china",
                timeout=120, capture_output=True, text=True
            )
            print(r.stdout)
            if r.returncode == 0:
                return True
            if r.stderr:
                print(f"  [回退] stderr: {r.stderr}")
        except subprocess.TimeoutExpired:
            print("  [回退] 超时")
        except Exception as e2:
            print(f"  [回退] 异常: {e2}")
    else:
        print(f"  [回退] 外部脚本不存在: {ext}")

    return False
