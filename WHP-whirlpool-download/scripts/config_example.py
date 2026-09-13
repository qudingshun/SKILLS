#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一报表下载工具 - 运行时配置示例
=====================================================

使用方法：
1. 复制此文件为 runtime_config.json
2. 修改以下字段为你的实际信息
3. 运行 unified_report_downloader.py

安全提示：
- 强烈建议使用加密密码存储（见 secure_password_manager）
- 配置文件和加密密码文件请妥善保管，不要泄露给他人
"""

import json
import sys
from datetime import datetime

# 安全输出函数
try:
    from whirlpool_common import safe_print
except ImportError:
    def safe_print(*args, **kwargs):
        print(*args, **kwargs)

# ═══════════════════════════════════════════════════════
# SCM 系统配置
# ═══════════════════════════════════════════════════════
SCM_CONFIG = {
    # ── 登录信息 ────────────────────────────────────────
    "username": "hsa697",              # ← 修改为你的 SCM 用户名
    
    # 密码建议：使用加密方式存储，不要明文保存！
    # 选项 1: 直接填写明文（不推荐）
    # "password": "***REMOVED***"
    
    # 选项 2: 使用加密（推荐）- 运行脚本后会自动生成加密密码
    # 首次运行时，系统会提示你输入明文密码进行加密存储
    "password": "",                    # ← 留空，首次运行将自动加密
    
    # ── 查询参数 ────────────────────────────────────────
    "audit_date": "2026-04-01",        # 请购单审核日期（仅任务 5 需要）
    
    "shipment_date_start": "2026-07-17",  # 送货单产生开始日期（任务 2 送货单查询需要，截至日期自动取当天）
    
    # ── 下载目录配置 ────────────────────────────────────
    "dir_task1": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\scm_task1",      # 送货通知查询结果目录
    "dir_task2": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\scm_task2",      # 送货单查询结果目录  
    "dir_task3": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\scm_task3",      # PO 未结量汇总查询结果目录
    "dir_task4": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\scm_task4",      # 回货计划发放结果目录
    "dir_task5": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\scm_task5",      # 请购单查询结果目录
    
    # ── 可选：自定义 SCM URL（默认使用 https://scm.whirlpool-china.com:7580/websrm/）
    # "custom_url": ""
}

# ═══════════════════════════════════════════════════════
# 帆软报表系统配置
# ═══════════════════════════════════════════════════════
FANRUAN_CONFIG = {
    # ── 登录信息 ────────────────────────────────────────
    "username": "HSA697",              # ← 修改为你的帆软用户名
    
    # 密码建议：使用加密方式存储（推荐）或明文（不推荐）
    "password": "",                    # ← 留空，首次运行将自动加密
    
    # ── 工厂信息 ────────────────────────────────────────
    "factory_code": "664",            # 三工厂代码
    
    # ── 下载目录配置 ────────────────────────────────────
    "dir_bom": r"D:\360 安全浏览器下载\bom",         # BOM 循环查询结果目录
    "dir_report1": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\report1", # 已发放工单推式料发料明细目录
    "dir_report2": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\report2", # SCM 转订单无效清单目录  
    "dir_stock": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\stock",     # 库存报表目录
    
    # ── OA 物料编码来源（仅 BOM 任务需要）───────────────
    # 如果 BOM 循环查询需要读取物料编码，可指定 Excel 路径
    "oa_plan_dir": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\oa_plan",   # 计划.xlsx 所在目录
}

# ═══════════════════════════════════════════════════════
# OA 系统配置（可选）
# ═══════════════════════════════════════════════════════
OA_CONFIG = {
    "plan_dir": r"E:\OneDrive\桌面\桌面临时文件\PMC 小工具\回货引用文件\加载文件\oa_plan",  # OA 计划文件所在目录（BOM 任务需要）
}

# ═══════════════════════════════════════════════════════
# 保存配置到 JSON 文件
# ═══════════════════════════════════════════════════════

def save_config():
    """将配置保存到 runtime_config.json"""
    config = {
        "scm": SCM_CONFIG,
        "fanruan": FANRUAN_CONFIG,
        "oa": OA_CONFIG,
        "created_at": datetime.now().isoformat(),
    }
    
    with open("runtime_config.json", 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print("[配置] 已保存至 runtime_config.json")

# ── 首次运行自动加密密码 ────────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    # 检查是否第一次运行（没有现有配置文件）
    try:
        with open("runtime_config.json", 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # 如果密码字段为空，提示用户加密
        if not config["scm"]["password"] and not config["fanruan"]["password"]:
            print("\n" + "=" * 60)
            print("  首次运行检测到未加密的密码")
            print("=" * 60)
            
            # SCM 密码加密
            scm_password = input("请输入 SCM 密码：").strip()
            if scm_password:
                config["scm"]["password"] = scm_password
                
                from secure_config import SecurePasswordManager, ConfigManager
                manager = ConfigManager("runtime_config.json")
                secure_manager = SecurePasswordManager(manager)
                
                # 保存加密后的密码
                secure_manager.save_password("scm", "hsa697", scm_password)
                print("[安全] SCM 密码已加密存储")
            
            # 帆软密码加密
            fanruan_password = input("请输入帆软密码：").strip()
            if fanruan_password:
                config["fanruan"]["password"] = fanruan_password
                
                from secure_config import SecurePasswordManager, ConfigManager
                manager = ConfigManager("runtime_config.json")
                secure_manager = SecurePasswordManager(manager)
                
                # 保存加密后的密码
                secure_manager.save_password("fanruan", "HSA697", fanruan_password)
                print("[安全] 帆软密码已加密存储")
            
            save_config()
        else:
            # 已有配置文件，直接保存
            save_config()
            
    except Exception as e:
        safe_print(f"[配置] 首次运行设置失败：{e}")
