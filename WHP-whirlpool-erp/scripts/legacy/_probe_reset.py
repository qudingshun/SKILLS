# -*- coding: utf-8 -*-
"""探针：验证「改表头说明是否会把底部组织/地点/子库存重置」。"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ui, erp_forms, erp_navigator
import erp_flow_requisition_full as F

APP = erp_forms.FormsApp()
APP.connect_by_hwnd(list(erp_navigator.snapshot_forms_windows())[-1])


def bottom_state(tag):
    img, hits = F.look(APP)
    st = {}
    for f, y, k in (("组织", 705, "洗衣机三"), ("地点", 745, "洗衣机三"),
                    ("子库存", 779, "WL301")):
        v = F._field_has_value(hits, 323, y, k, f)
        st[f] = v
    print(tag, st)
    return st


img, hits = F.look(APP)
rows, xf = F.bottom_rows(hits, 410 + 224)
print("rows", rows)

# 1) 先填底部
for f, v, k in (("组织", "洗衣机三工厂", "洗衣机三"),
                ("地点", "洗衣机三工厂", "洗衣机三"),
                ("子库存", "WL301", "WL301")):
    print(f, F.fill_bottom(APP, f, v, rows, xf, k))
bottom_state("after fill")

# 2) 点表格编号提交
img, hits = F.look(APP)
F.click_at(APP, 106, 446, "编号"); time.sleep(1.2)
bottom_state("after commit")

# 3) 改表头说明（换成另一个值）再提交
lay = F.layout_right(*F.look(APP))
print("desc fill", F.fill_header_desc(APP, lay, "测试说明变更", "测试说明变更"))
F.click_at(APP, 106, 446, "编号"); time.sleep(1.5)
bottom_state("after desc commit")
erp_ui.capture(APP, focus=False).save(
    r"E:\SKILLS\WHP-whirlpool-erp\logs\probe_reset.png")
