# -*- coding: utf-8 -*-
"""
惠而浦物料多表综合查询脚本
用法: python query.py <料号>
输出: JSON 汇总（stdout）
"""
import sys
import json
import os
import warnings
from collections import OrderedDict

warnings.filterwarnings("ignore")  # 屏蔽 openpyxl 的无害 UserWarning(默认样式缺失等)

import openpyxl

BASE = r"E:\OneDrive\桌面\桌面临时文件\PMC小工具\回货引用文件\加载文件"


def _load(path):
    # 注意: 不能使用 read_only=True。库存报表.xlsx 的文件 dimension 元数据损坏，
    # read_only 模式只会读到声明行数(1行)，丢失全部真实数据。read_only=False 正常。
    wb = openpyxl.load_workbook(path, read_only=False, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    return rows


def strip15(v):
    if v is None:
        return ""
    return str(v).strip().replace(".0", "")


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "缺少料号参数"}, ensure_ascii=False))
        return
    mat = sys.argv[1].strip()
    if mat.endswith("-"):
        mat = mat  # 保留末尾横杠作为合法字符
    mat_l = mat.lower()

    result = OrderedDict()
    result["料号"] = mat

    # ---------- 1. 库存报表 ----------
    try:
        rows = _load(os.path.join(BASE, "库存报表.xlsx"))
        inv = []
        for r in rows[2:]:  # 表头在第2行(索引1)，数据从第3行(索引2)开始
            if r is None or len(r) < 8:
                continue
            material, org, wh, pos, qty = r[0], r[2], r[3], r[5], r[6]
            if org == "M03" and wh == "WL301" and strip15(material).lower() == mat_l:
                pos_s = "由内置货位" if not pos else str(pos).strip()
                sup_code = ""
                sup_name = ""
                if pos and "/" in str(pos):
                    left = str(pos).split("/", 1)[0].strip()
                    right = str(pos).split("/", 1)[1].strip().replace("WL", "").strip()
                    sup_code = left
                    sup_name = right
                inv.append({
                    "货位": str(pos) if pos else "",
                    "供应商编码": sup_code,
                    "供应商名称": sup_name,
                    "库存数量": qty if qty is not None else 0,
                })
        result["库存(M03/WL301)"] = inv

        # 库存补充列：组织=M03，库位∈{Y0001,Y0002,Y0003} 的合计数量（不分供应商）
        # 注意: 需要单独再遍历全表（read_only=False 下可重复迭代 rows 列表）
        y_sum = 0
        y_warehouses = {"Y0001", "Y0002", "Y0003"}
        for r in rows[2:]:
            if r is None or len(r) < 8:
                continue
            if r[2] == "M03" and r[3] in y_warehouses and strip15(r[0]).lower() == mat_l:
                v = r[6] if r[6] is not None else 0
                y_sum += v
        result["库存(M03/Y0001+Y0002+Y0003)"] = y_sum
    except Exception as e:
        result["库存(M03/WL301)"] = {"error": str(e)}
        result["库存(M03/Y0001+Y0002+Y0003)"] = {"error": str(e)}

    # ---------- 2. 送货单查询 ----------
    try:
        rows = _load(os.path.join(BASE, "送货单查询.xlsx"))
        hdr = rows[0]
        idx = {name: i for i, name in enumerate(hdr)}
        # 列名定位
        col_recv = idx.get("是否接收")
        col_ins = idx.get("是否报检")
        col_mat = idx.get("物料编码")
        col_supc = idx.get("供应商编码")
        col_supn = idx.get("供应商名称")
        col_qty = idx.get("送货数量")
        col_insq = idx.get("报检数量")

        deliver = OrderedDict()   # 未接收+未报检 -> 送货数量 (按供应商)
        inspect = OrderedDict()   # 未接收+已报检 -> 报检数量 (按供应商)
        for r in rows[1:]:
            if r is None:
                continue
            if strip15(r[col_mat]).lower() != mat_l:
                continue
            recv = str(r[col_recv]).strip() if r[col_recv] else ""
            ins = str(r[col_ins]).strip() if r[col_ins] else ""
            key = (strip15(r[col_supc]), strip15(r[col_supn]))
            if recv == "未接收" and ins == "未报检":
                v = r[col_qty] if r[col_qty] is not None else 0
                deliver[key] = deliver.get(key, 0) + v
            if recv == "未接收" and ins == "已报检":
                v = r[col_insq] if r[col_insq] is not None else 0
                inspect[key] = inspect.get(key, 0) + v
        result["送货未接收未报检"] = [{"供应商编码": k[0], "供应商名称": k[1], "送货数量": v} for k, v in deliver.items()]
        result["送货未接收已报检"] = [{"供应商编码": k[0], "供应商名称": k[1], "报检数量": v} for k, v in inspect.items()]
    except Exception as e:
        result["送货未接收未报检"] = {"error": str(e)}
        result["送货未接收已报检"] = {"error": str(e)}

    # ---------- 3. 送货通知查询 (未制单量) ----------
    try:
        rows = _load(os.path.join(BASE, "送货通知查询.xlsx"))
        hdr = rows[0]
        idx = {name: i for i, name in enumerate(hdr)}
        col_mat = idx.get("物料编码")
        col_supc = idx.get("供应商编码")
        col_supn = idx.get("供应商名称")
        col_w = idx.get("未制单量")
        notify = OrderedDict()
        for r in rows[1:]:
            if r is None:
                continue
            if strip15(r[col_mat]).lower() != mat_l:
                continue
            key = (strip15(r[col_supc]), strip15(r[col_supn]))
            v = r[col_w] if r[col_w] is not None else 0
            notify[key] = notify.get(key, 0) + v
        result["送货通知未制单量"] = [{"供应商编码": k[0], "供应商名称": k[1], "未制单量": v} for k, v in notify.items()]
    except Exception as e:
        result["送货通知未制单量"] = {"error": str(e)}

    # ---------- 4. 采购订单未结量 (剩余可发布送货通知总量) ----------
    try:
        rows = _load(os.path.join(BASE, "采购订单未结量物料汇总查询.xlsx"))
        hdr = rows[0]
        idx = {name: i for i, name in enumerate(hdr)}
        col_mat = idx.get("物料编码")
        col_supc = idx.get("供应商编码")
        col_supn = idx.get("供应商名称")
        col_r = idx.get("剩余可发布送货通知总量")
        order_left = OrderedDict()
        for r in rows[1:]:
            if r is None:
                continue
            if strip15(r[col_mat]).lower() != mat_l:
                continue
            key = (strip15(r[col_supc]), strip15(r[col_supn]))
            v = r[col_r] if r[col_r] is not None else 0
            order_left[key] = order_left.get(key, 0) + v
        result["采购订单剩余可发布量"] = [{"供应商编码": k[0], "供应商名称": k[1], "剩余可发布送货通知总量": v} for k, v in order_left.items()]
    except Exception as e:
        result["采购订单剩余可发布量"] = {"error": str(e)}

    # ---------- 5. 回货计划发放 (未分配量, 不分供应商) ----------
    try:
        rows = _load(os.path.join(BASE, "回货计划发放.xlsx"))
        hdr = rows[0]
        idx = {name: i for i, name in enumerate(hdr)}
        col_mat = idx.get("物料编码")
        col_ship = idx.get("可下发送货通知")
        col_una = idx.get("未分配量")
        huihuo_no = 0
        huihuo_yes = 0
        for r in rows[1:]:
            if r is None:
                continue
            if strip15(r[col_mat]).lower() != mat_l:
                continue
            ship = str(r[col_ship]).strip() if r[col_ship] else ""
            v = r[col_una] if r[col_una] is not None else 0
            if ship == "否":
                huihuo_no += v
            elif ship == "是":
                huihuo_yes += v
        result["回货计划(不分供应商)"] = {
            "可下发送货通知=否的未分配量": huihuo_no,
            "可下发送货通知=是的未分配量": huihuo_yes,
        }
    except Exception as e:
        result["回货计划(不分供应商)"] = {"error": str(e)}

    # ---------- 6. 请购单查询 (行状态=打开, 不分供应商) ----------
    try:
        rows = _load(os.path.join(BASE, "请购单查询.xlsx"))
        hdr = rows[0]
        idx = {name: i for i, name in enumerate(hdr)}
        col_mat = idx.get("物料编码")
        col_status = idx.get("行状态")
        col_q = idx.get("请购单总数量")
        pr_total = 0
        for r in rows[1:]:
            if r is None:
                continue
            if strip15(r[col_mat]).lower() != mat_l:
                continue
            status = str(r[col_status]).strip() if r[col_status] else ""
            if status == "打开":
                v = r[col_q] if r[col_q] is not None else 0
                pr_total += v
        result["请购单(不分供应商, 行状态=打开)"] = pr_total
    except Exception as e:
        result["请购单(不分供应商, 行状态=打开)"] = {"error": str(e)}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
