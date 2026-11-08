# -*- coding: utf-8 -*-
"""临时驱动：在当前 javaws 起的 applet 上继续「选工厂 → 2.申请 → 打开」，
   到达 申请-[新建] 后录入 → 校验 →（--save 时）保存并审批。（不要交付）
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_flow_requisition_full as F
import erp_forms
import erp_ui
import erp_navigator

ap = argparse.ArgumentParser()
ap.add_argument("--save", action="store_true")
ap.add_argument("--req", default="采购订单失效补录|301B120034004:300,301B120030221:988")
ap.add_argument("--days", type=int, default=7)
args = ap.parse_args()

cfg = F.build_cfg(args)
doc = cfg["docs"][0]
print("plan:", doc["desc"], doc["lines"], flush=True)

snap = erp_navigator.snapshot_forms_windows()
print("applets:", snap, flush=True)
if not snap:
    sys.exit("没有 applet 窗口")
hwnd = list(snap)[0]
app = erp_forms.FormsApp()
if not app.connect_by_hwnd(hwnd):
    sys.exit("连接 applet 失败")
F.force_foreground(hwnd)
erp_ui.focus_window(app, settle=2.0)

img, hits = F.look(app, focus=True)
F.save_shot(img, os.path.join(F.LOGS, "drv_01_start.png"))

# ① 选工厂
row = F.find_tok(hits, F.FACTORY, x_min=100, x_max=320)
if row is None:
    lab = F.find_tok(hits, "组织", y_min=520, exact=True)
    if lab:
        F.click_at(app, lab[2].x + lab[2].w + 120, lab[2].y + lab[2].h // 2, "组织字段")
        time.sleep(2.0)
    t0 = time.time()
    while time.time() - t0 < 45 and row is None:
        img, hits = F.look(app, focus=True)
        row = F.find_tok(hits, F.FACTORY, x_min=100, x_max=320)
        if row is None:
            time.sleep(2.0)
if row is None:
    F.save_shot(img, os.path.join(F.LOGS, "drv_fail_org.png"))
    sys.exit("找不到工厂行")
F.click_at(app, row[2].center[0], row[2].center[1], F.FACTORY)
time.sleep(0.8)
okb = F.find_tok(F.look(app)[1], "确定", y_min=300)
if okb is None:
    sys.exit("工厂 LOV 没有确定")
erp_ui.click_rect(app, okb[2], dx=0.5, dy=0.5)
time.sleep(2.5)
print("[OK] 工厂已选", flush=True)

# ② 常用表单 2.申请
item = None
t0 = time.time()
while time.time() - t0 < 40 and item is None:
    img, hits = F.look(app, focus=True)
    for t, s, r in hits:
        if t.strip().lstrip("0123456789.、． ") == F.WORD_APPLY and r.x > 380:
            item = (t, s, r)
    if item is None:
        time.sleep(2.0)
if item is None:
    F.save_shot(img, os.path.join(F.LOGS, "drv_fail_apply.png"))
    sys.exit("常用表单里没有 2.申请")
erp_ui.click_rect(app, item[2], dx=0.5, dy=0.5)
time.sleep(0.8)
btn = F.find_tok(F.look(app)[1], "打开", y_min=450)
if btn is None:
    sys.exit("找不到 打开(Q)")
erp_ui.click_rect(app, btn[2], dx=0.5, dy=0.5)
time.sleep(6.0)
n = F.dismiss_dialogs(app)
print("[OK] 已点打开，弹窗", n, flush=True)

# ③ 找申请窗口（可能新开 applet）
app2, target, img, hits = None, None, None, []
t0 = time.time()
while time.time() - t0 < 75:
    snap = erp_navigator.snapshot_forms_windows()
    for h in list(snap):
        cand = erp_forms.FormsApp()
        if not cand.connect_by_hwnd(h):
            continue
        F.force_foreground(h)
        im = F.grab(cand, focus=True)
        if im is None or im.width < 800 or im.height < 600:
            continue
        hs = F.ocr_hits(im)
        txt = " ".join(t for t, s, r in hs)
        if any(k in txt for k in ("申请", "编号", "业务实体", "物料")):
            app2, target, img, hits = cand, h, im, hs
            print(f"[OK] 申请窗口 hwnd={h}", flush=True)
            break
        print(f"[info] hwnd={h} 还没画出申请表单：{txt[:40]}", flush=True)
    if app2 is not None:
        break
    time.sleep(3)
if app2 is None:
    sys.exit("没有申请窗口")
F.save_shot(img, os.path.join(F.LOGS, "drv_02_form.png"))

lay = F.layout_from(hits)
if lay is None:
    img, hits, lay = F.scroll_to_grid_header(app2)
if lay is None:
    F.save_shot(img, os.path.join(F.LOGS, "drv_fail_layout.png"))
    sys.exit("没识别到表格表头（右视图）")

print("[go] 开始录入", flush=True)
ok, lay, row_ys = F.fill_doc(app2, doc, cfg)
if not ok:
    F.save_shot(F.grab(app2) or img, os.path.join(F.LOGS, "drv_fail_fill.png"))
    sys.exit("录入失败")

img, hits = F.look(app2)
final_ok, rep = F.verify_doc(img, hits, lay, doc, cfg, row_ys)
F.print_report(rep)
F.save_shot(img, os.path.join(F.LOGS, "drv_03_filled.png"))
if not final_ok:
    print("校验未通过，未保存：", [k for k, v in rep.items() if not v[0]], flush=True)
    sys.exit(1)
print("[OK] 校验通过", flush=True)

if args.save:
    num, img = F.save_doc(app2)
    print("申请编号:", num, flush=True)
    if num:
        aproved = F.approve_doc(app2)
        print("审批提交:", aproved, flush=True)
        img, hits = F.look(app2)
        F.save_shot(img, os.path.join(F.LOGS, f"drv_done_{num}.png"))
        print("MEDIA:" + os.path.join(F.LOGS, f"drv_done_{num}.png"), flush=True)
