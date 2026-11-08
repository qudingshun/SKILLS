# -*- coding: utf-8 -*-
"""临时探针：验证第 2 行新建+录入+整单校验。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ui, erp_forms, erp_navigator
import erp_flow_requisition_full as F

snap = erp_navigator.snapshot_forms_windows()
APP = erp_forms.FormsApp()
APP.connect_by_hwnd(list(snap)[-1])

img, hits = F.look(APP)
row1 = F.row1_y_from(hits)
step = F.detect_row_step(F.to_bgr(img), row1)
print("row1", row1, "step", step)

y2 = F.create_next_line(APP, row1)
print("new row y", y2)

line2 = {"item": "301B120030221", "qty": "988", "price": "0", "date": "2026-11-03"}
print("fill line2 =", F.fill_one_line(APP, y2, line2, "行2·"))

img, hits = F.look(APP)
lay = F.layout_right(img, hits)
doc = {"desc": "采购订单失效补录",
       "lines": [{"item": "301B120034004", "qty": "300", "price": "0", "date": "2026-11-03"},
                 line2]}
cfg = {"desc_core": "采购订单失效补录"}
ok, rep = F.verify_doc(img, hits, lay, doc, cfg, [row1, y2])
F.print_report(rep)
print("VERIFY =", ok)
erp_ui.capture(APP, focus=False).save(r"E:\SKILLS\WHP-whirlpool-erp\logs\probe_row2.png")
