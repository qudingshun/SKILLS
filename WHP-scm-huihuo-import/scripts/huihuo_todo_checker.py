#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回货待办整合脚本
功能：
1. 解析用户回货指令（料号+数量）
2. 读取本地报表数据（如超过1小时则先下载SCM报表）
3. 判断采购订单剩余是否满足回货数量
4. 满足→调用WHP-scm-huihuo-import执行回货
5. 不满足→按实际可用数量回货，未完成部分写入待办文件

用法：
  py scripts/huihuo_todo_checker.py --data "PF1065 30000, 3002880202140 5000" --date "2026-10-31" --remarks "10月注塑需求"
  py scripts/huihuo_todo_checker.py --material "PF1065" --qty "30000" --date "2026-10-31"
"""

import argparse
import json
import os
import sys
import subprocess
import shutil
from datetime import datetime, timedelta
from pathlib import Path

# 路径配置
SKILL_DIR = Path(r"E:\SKILLS\WHP-scm-huihuo-import")
SCRIPTS_DIR = SKILL_DIR / "scripts"
QUERY_SCRIPT = r"E:\SKILLS\material-inventory-check\scripts\query.py"
DOWNLOAD_SCRIPT = r"E:\SKILLS\WHP-whirlpool-download\scripts\run.js"
VENV_PYTHON = r"E:\SKILLS\.venv\Scripts\python.exe"
TODO_FILE = SKILL_DIR / "logs" / "todo.md"

# 报表数据目录
DATA_DIR = r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件"
PO_FILE = os.path.join(DATA_DIR, "采购订单未结量物料汇总查询.xlsx")
HUIHUO_FILE = os.path.join(DATA_DIR, "回货计划发放.xlsx")
PR_FILE = os.path.join(DATA_DIR, "请购单查询.xlsx")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [TODO-CHECKER] {msg}")


def download_scm_reports():
    """调用报表下载技能下载 SCM 报表"""
    log("正在下载 SCM 报表...")
    cmd = ["node", DOWNLOAD_SCRIPT, "--module", "scm"]
    try:
        result = subprocess.run(
            cmd,
            cwd=r"E:\SKILLS\WHP-whirlpool-download",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        if result.returncode == 0:
            log("全量报表下载成功")
            return True
        else:
            log(f"全量报表下载失败：exit={result.returncode}")
            log(f"stderr: {result.stderr[:500]}")
            return False
    except subprocess.TimeoutExpired:
        log("全量报表下载超时")
        return False
    except Exception as e:
        log(f"SCM 报表下载异常：{e}")
        return False


def check_file_age(file_path, max_age_minutes=60):
    """检查文件是否在max_age_minutes内更新过"""
    if not os.path.exists(file_path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
    return (datetime.now() - mtime) < timedelta(minutes=max_age_minutes)


def query_material(material_code):
    """调用material-inventory-check查询料号数据"""
    log(f"查询料号: {material_code}")
    try:
        result = subprocess.run(
            [VENV_PYTHON, QUERY_SCRIPT, material_code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data
        else:
            log(f"查询失败: {result.stderr[:300]}")
            return None
    except subprocess.TimeoutExpired:
        log("查询超时")
        return None
    except Exception as e:
        log(f"查询异常: {e}")
        return None


def extract_po_data(data):
    """从查询结果提取采购订单和回货计划数据"""
    po_remaining = 0
    pr_total = 0
    huihuo_yes_unassigned = 0  # 未分配已回货数量（可下发送货通知=是）

    # 采购订单剩余
    for item in data.get("采购订单剩余可发布量", []):
        po_remaining += item.get("剩余可发布送货通知总量", 0)

    # 采购申请（请购单）
    pr_total = data.get("请购单(不分供应商, 行状态=下达)", 0)

    # 回货计划中"可下发送货通知=是"的未分配量（已回货但未分配）
    huihuo_plan = data.get("回货计划(不分供应商)", {})
    huihuo_yes_unassigned = huihuo_plan.get("可下发送货通知=是的未分配量", 0)

    return po_remaining, pr_total, huihuo_yes_unassigned


def run_huihuo_import(data_str, date_str, remarks, headless=False):
    """调用WHP-scm-huihuo-import执行回货"""
    cmd = ["node", str(SCRIPTS_DIR / "run.js"), "--data", data_str]
    if date_str:
        cmd += ["--date", date_str]
    if remarks:
        cmd += ["--remarks", remarks]
    if headless:
        cmd += ["--headless"]

    log(f"执行回货: {data_str}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(SKILL_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
        )
        success = result.returncode == 0
        if success:
            log("回货执行成功")
        else:
            log(f"回货执行失败: exit={result.returncode}")
        return success
    except subprocess.TimeoutExpired:
        log("回货执行超时")
        return False
    except Exception as e:
        log(f"回货执行异常: {e}")
        return False


def read_todo_table():
    """读取待办文件"""
    if not TODO_FILE.exists():
        return []
    with open(TODO_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    return content


def write_todo_table(content):
    """写入待办文件"""
    TODO_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TODO_FILE, "w", encoding="utf-8") as f:
        f.write(content)


def add_todo_item(material_code, planned_qty, released_qty, po_remaining, huihuo_yes_unassigned, pr_total):
    """添加待办事项到汇总表"""
    actual_available = po_remaining - huihuo_yes_unassigned
    unfulfilled = planned_qty - released_qty

    content = read_todo_table()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 检查是否已存在该料号的待办
    lines = content.split("\n")
    found = False
    new_lines = []
    for line in lines:
        if material_code in line and "|" in line:
            # 更新现有行
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 10:
                parts[3] = str(released_qty)  # 已回货
                parts[4] = str(unfulfilled)   # 未回货
                parts[5] = str(po_remaining)  # 采购订单剩余
                parts[6] = str(huihuo_yes_unassigned)  # 未分配已回货
                parts[7] = str(actual_available)  # 实际可用
                parts[8] = str(pr_total)  # 采购申请
                parts[9] = "❌" if actual_available < unfulfilled else "✅"
                line = " | ".join(parts)
            found = True
        new_lines.append(line)

    if not found:
        # 新增行
        can_handle = "✅" if actual_available >= unfulfilled else "❌"
        new_row = f"| - | {material_code} | {planned_qty:,} | {released_qty:,} | {unfulfilled:,} | {po_remaining:,} | {huihuo_yes_unassigned:,} | {actual_available:,} | {pr_total:,} | {can_handle} |"
        # 找到表格末尾（空行前）插入
        for i, line in enumerate(new_lines):
            if line.strip() == "" and i > 0 and "---" not in new_lines[i-1]:
                new_lines.insert(i, new_row)
                break
        else:
            new_lines.append(new_row)

    # 更新时间戳
    content = "\n".join(new_lines)
    content = content.replace(
        "**更新时间：",
        f"**更新时间：{now_str} | 备注：10月需求 | "
    )

    write_todo_table(content)
    log(f"待办文件已更新: {material_code} 未回货 {unfulfilled}")


def main():
    parser = argparse.ArgumentParser(description="回货待办整合脚本")
    parser.add_argument("--data", help="多行回货数据: 'code qty remarks, code qty'")
    parser.add_argument("--material", help="单个料号")
    parser.add_argument("--qty", help="单个数量")
    parser.add_argument("--date", help="回货日期 YYYY-MM-DD")
    parser.add_argument("--remarks", default="", help="备注")
    parser.add_argument("--headless", action="store_true", help="无头模式")
    parser.add_argument("--force-download", action="store_true", help="强制下载最新报表")
    args = parser.parse_args()

    # 解析回货数据
    items = []
    if args.data:
        for pair in args.data.split(","):
            parts = pair.strip().split()
            if len(parts) >= 2:
                code, qty = parts[0], int(parts[1])
                remark = " ".join(parts[2:]) if len(parts) > 2 else args.remarks
                items.append((code, qty, remark))
    elif args.material and args.qty:
        items.append((args.material, int(args.qty), args.remarks))
    else:
        print("错误：需要提供 --data 或 --material+--qty 参数")
        sys.exit(1)

    log(f"待处理回货: {len(items)} 条")
    log(f"日期: {args.date or '默认(当月最后一天)'} | 备注: {args.remarks or '无'}")

    # 步骤 1: 检查报表文件年龄，如超过 1 小时则下载
    po_age_ok = check_file_age(PO_FILE, 60)
    huihuo_age_ok = check_file_age(HUIHUO_FILE, 60)
    pr_age_ok = check_file_age(PR_FILE, 60)

    if args.force_download or not (po_age_ok and huihuo_age_ok and pr_age_ok):
        log("报表文件超过 1 小时或强制下载，正在更新 SCM 报表...")
        if not download_scm_reports():
            log("报表下载失败，使用现有数据继续...")
    else:
        log("报表文件在1小时内，直接使用现有数据")

    # 步骤2: 逐条处理回货
    for material_code, planned_qty, remarks in items:
        log(f"\n{'='*50}")
        log(f"处理: {material_code} x{planned_qty}")

        # 查询最新数据
        data = query_material(material_code)
        if not data:
            log(f"查询失败，跳过 {material_code}")
            continue

        po_remaining, pr_total, huihuo_yes_unassigned = extract_po_data(data)
        actual_available = po_remaining - huihuo_yes_unassigned

        log(f"采购订单剩余: {po_remaining} | 未分配已回货: {huihuo_yes_unassigned} | 实际可用: {actual_available} | 采购申请: {pr_total}")
        log(f"本次要求: {planned_qty}")

        # 判断是否能满足
        if actual_available >= planned_qty:
            # 满足→按要求的数量回货
            log(f"满足，执行回货 {planned_qty}")
            data_str = f"{material_code} {planned_qty}"
            if remarks:
                data_str += f" {remarks}"
            success = run_huihuo_import(data_str, args.date, "", args.headless)
            if success:
                released_qty = planned_qty
                unfulfilled = 0
            else:
                released_qty = 0
                unfulfilled = planned_qty
        else:
            # 不满足→按实际可用数量回货
            log(f"不满足，按实际可用 {actual_available} 执行回货")
            if actual_available > 0:
                data_str = f"{material_code} {actual_available}"
                if remarks:
                    data_str += f" {remarks}"
                success = run_huihuo_import(data_str, args.date, "", args.headless)
                if success:
                    released_qty = actual_available
                    unfulfilled = planned_qty - actual_available
                else:
                    released_qty = 0
                    unfulfilled = planned_qty
            else:
                log(f"实际可用为0，无法回货")
                released_qty = 0
                unfulfilled = planned_qty

        # 步骤3: 更新待办
        add_todo_item(material_code, planned_qty, released_qty, po_remaining, huihuo_yes_unassigned, pr_total)
        log(f"结果: 已回货 {released_qty}, 未回货 {unfulfilled}")

    log("\n全部处理完成")


if __name__ == "__main__":
    main()
