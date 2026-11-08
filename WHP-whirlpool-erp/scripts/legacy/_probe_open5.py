# -*- coding: utf-8 -*-
"""临时探针 5：打开申请后先空等 60s（不点任何东西），看 applet 是否自己报 FRM-92102（不要交付）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_flow_requisition_full as F
import erp_navigator
import erp_forms
import erp_ui
from PIL import ImageGrab

RESP = F.RESP


def shot(tag, n):
    p = os.path.join(F.LOGS, f"po5_{n:02d}_{tag}.png")
    ImageGrab.grab().save(p)
    print(f"[shot] {p}", flush=True)


def state(app, tag):
    img, hits = F.look(app)
    txt = " ".join(t for t, s, r in hits)
    frm = "FRM-92102" in txt
    print(f"[state {tag}] n_hits={len(hits)} FRM={frm} text[:120]={txt[:120]}",
          flush=True)
    return frm


ie = F.erp_ie11.open_and_login(visible=True, lang="ZHS")
erp_navigator.expand_responsibility(ie, RESP)
url = erp_navigator.read_function_url(ie, "更改组织", resp_name=RESP)
before = erp_navigator.snapshot_forms_windows()
erp_navigator.open_forms_window(url)
hwnd = None
for _ in range(40):
    time.sleep(3)
    for h in erp_navigator.snapshot_forms_windows():
        if h not in before:
            hwnd = h
            break
    if hwnd:
        break
print("applet hwnd", hwnd, flush=True)
app = erp_forms.FormsApp()
print("connect", app.connect_by_hwnd(hwnd), flush=True)
F.force_foreground(hwnd)
erp_ui.focus_window(app, settle=2.0)

# 组织 → 确定 → 2.申请 → 打开（与主流程一致）
img, hits = F.look(app, focus=True)
row = F.find_tok(hits, F.FACTORY, x_min=100, x_max=320)
print("factory", bool(row), flush=True)
F.click_at(app, row[2].center[0], row[2].center[1], F.FACTORY)
time.sleep(1.0)
okb = F.find_tok(F.look(app)[1], "确定", y_min=300)
erp_ui.click_rect(app, okb[2], dx=0.5, dy=0.5)
time.sleep(2.5)
item = None
t0 = time.time()
while time.time() - t0 < 40 and item is None:
    img, hits = F.look(app, focus=True)
    for t, s, r in hits:
        if t.strip().lstrip("0123456789.、． ") == F.WORD_APPLY and r.x > 380:
            item = (t, s, r)
    if item is None:
        time.sleep(2.0)
erp_ui.click_rect(app, item[2], dx=0.5, dy=0.5)
time.sleep(0.8)
btn = F.find_tok(F.look(app)[1], "打开", y_min=450)
erp_ui.click_rect(app, btn[2], dx=0.5, dy=0.5)
print("[open] clicked 打开", flush=True)

for i in range(7):
    time.sleep(10)
    died = state(app, f"idle_{(i + 1) * 10}s")
    shot(f"idle{(i + 1) * 10}", i + 1)
    if died:
        print("[STOP] 出现 FRM-92102", flush=True)
        break
print("done", flush=True)
