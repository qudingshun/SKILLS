# -*- coding: utf-8 -*-
"""
获取物料名称脚本
用法: python get_mat_names.py <料号1> [料号2] [料号3] ...
输出: JSON {料号: 物料名称, ...}

数据源: 请购单查询.xlsx > 采购订单未结量.xlsx > 送货单查询.xlsx
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import openpyxl

BASE = r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件"

# 列索引定义
COL_MAP = {
    "请购单查询.xlsx": {"mat_col": 13, "name_col": 14},
    "采购订单未结量物料汇总查询.xlsx": {"mat_col": 4, "name_col": 5},
    "送货单查询.xlsx": {"mat_col": 0, "name_col": 1},
    "库存报表.xlsx": {"mat_col": 0, "name_col": 1},
}


def get_name_from_file(filename, mat):
    """从指定文件获取物料名称"""
    try:
        path = os.path.join(BASE, filename)
        if not os.path.exists(path):
            return ""
        wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()

        if len(rows) < 2:
            return ""

        cols = COL_MAP.get(filename, {"mat_col": 0, "name_col": 1})
        mat_col = cols["mat_col"]
        name_col = cols["name_col"]

        mat_lower = mat.lower().strip()
        for r in rows[1:]:
            if r and len(r) > max(mat_col, name_col):
                cell_val = r[mat_col]
                if cell_val and mat_lower in str(cell_val).lower():
                    name_val = r[name_col]
                    if name_val:
                        return str(name_val).strip()
        return ""
    except Exception:
        return ""


def get_material_name(mat):
    """从多个数据源获取物料名称（优先级：请购单 > 采购订单 > 送货单 > 库存）"""
    for filename in [
        "请购单查询.xlsx",
        "采购订单未结量物料汇总查询.xlsx",
        "送货单查询.xlsx",
        "库存报表.xlsx",
    ]:
        name = get_name_from_file(filename, mat)
        if name:
            return name
    return ""


def main():
    if len(sys.argv) < 2:
        print("用法: python get_mat_names.py <料号1> [料号2] ...")
        print("输出: JSON {料号: 物料名称, ...}")
        return

    materials = [m.strip() for m in sys.argv[1:]]
    results = {}
    for mat in materials:
        if mat:
            results[mat] = get_material_name(mat)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
