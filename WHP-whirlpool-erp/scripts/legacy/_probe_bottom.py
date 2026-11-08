# -*- coding: utf-8 -*-
"""临时探针：在已打开的表单上验证底部 LOV 字段流程（不进库）。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import erp_ui, erp_forms, erp_navigator
import erp_flow_requisition_full as F


def dump(tag, y0=600, y1=1000):
    img = erp_ui.capture(APP, focus=False)
    hits = F.ocr_hits(img)
    rows = [(t, r.x, r.y) for t, s, r in hits if y0 <= r.y <= y1]
    print(f"--- {tag} ---")
    for t, x, y in rows:
        print(f"   {t!r:34} x={x:<5} y={y}")
    print("   lov_open =", F.lov_is_open(hits, 745))
    return img, hits


snap = erp_navigator.snapshot_forms_windows()
hwnd = list(snap)[-1]
APP = erp_forms.FormsApp()
assert APP.connect_by_hwnd(hwnd), "connect failed"
print("hwnd", hwnd)

lines = [{"item": "301B120034004", "qty": "300", "price": "0", "date": "2026-11-03"}]
ok = F.fill_one_line(APP, 410, lines[0], "行1·")
print("fill_one_line =", ok)
dump("after row1")

img, hits = F.look(APP)
rows, xf = F.bottom_rows(hits, 410 + 224)
print("bottom rows", rows, "x_field", xf)
print("bottom_rows type:", type(rows), rows)

for field, val, key in (("组织", "洗衣机三工厂", "洗衣机三"),
                        ("地点", "洗衣机三工厂", "洗衣机三"),
                        ("子库存", "WL301", "WL301")):
    r = F.fill_bottom(APP, field, val, rows, xf, key)
    print(f"fill_bottom({field}) = {r}")
    dump("after " + field)
