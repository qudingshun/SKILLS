"""OpenClaw 技能入口：成品库存日报生成工具"""
import sys
import os

# 将 scripts 目录添加到 sys.path，以便导入 inventory_daily
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from inventory_daily import run

if __name__ == "__main__":
    run()