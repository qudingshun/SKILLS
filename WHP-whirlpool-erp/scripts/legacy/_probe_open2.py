# -*- coding: utf-8 -*-
"""临时探针：复现「打开申请」每一步并截图，定位 applet 变白的时刻（不要交付）。"""
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
step = [0]


def shot(tag):
    step[0] += 1
    p = os.path.join(F.LOGS, f"po2_{step[0]:02d}_{tag}.png")
    ImageGrab.grab().save(p)
    print(f"[shot] {p}", flush=True)


def state(app=None, tag=""):
    img, hits = F.look(app) if app is not None else (None, [])
    txt = " ".join(t for t, s, r in hits)
    print(f"[state {tag}] applets={erp_navigator.snapshot_forms_windows()} "
          f"n_hits={len(hits)} text[:120]={txt[:120]}", flush=True)
    return img, hits


ie = F.erp_ie11.open_and_login(visible=True, lang="ZHS")
print("login", ie is not None and F.erp_ie11.is_logged_in(ie), flush=True)
print("expand", erp_navigator.expand_responsibility(ie, RESP), flush=True)
url = erp_navigator.read_function_url(ie, "更改组织", resp_name=RESP)
before = erp_navigator.snapshot_forms_windows()
ie2 = erp_navigator.open_forms_window(url)
print("dispatched", ie2 is not None, flush=True)

hwnd = None
for _ in range(40):
    time.sleep(3)
    snap = erp_navigator.snapshot_forms_windows()
    new = [h for h in snap if h not in before]
    if new:
        hwnd = new[0]
        break
print("applet hwnd", hwnd, flush=True)
if hwnd is None:
    sys.exit(1)

app = erp_forms.FormsApp()
print("connect", app.connect_by_hwnd(hwnd), flush=True)
F.force_foreground(hwnd)
erp_ui.focus_window(app, settle=2.0)
img, hits = state(app, "open")
shot("open")

row = F.find_tok(hits, F.FACTORY, x_min=100, x_max=320)
print("factory token", row, flush=True)
if row:
    F.click_at(app, row[2].center[0], row[2].center[1], F.FACTORY)
    time.sleep(1.0)
    shot("pick_factory")
    okb = F.find_tok(F.look(app)[1], "确定", y_min=300)
    print("确定 token", okb, flush=True)
    if okb:
        erp_ui.click_rect(app, okb[2], dx=0.5, dy=0.5)
        time.sleep(2.5)
        shot("after_ok")
        state(app, "after_ok")

item = None
t0 = time.time()
while time.time() - t0 < 40 and item is None:
    img, hits = F.look(app, focus=True)
    for t, s, r in hits:
        if t.strip().lstrip("0123456789.、． ") == F.WORD_APPLY and r.x > 380:
            item = (t, s, r)
    if item is None:
        time.sleep(2.0)
print("2.申请 token", item, flush=True)
if item:
    erp_ui.click_rect(app, item[2], dx=0.5, dy=0.5)
    time.sleep(0.8)
    shot("pick_apply")
    btn = F.find_tok(F.look(app)[1], "打开", y_min=450)
    print("打开 token", btn, flush=True)
    if btn:
        erp_ui.click_rect(app, btn[2], dx=0.5, dy=0.5)
        time.sleep(6.0)
        shot("after_open_6s")
        state(app, "after_open_6s")
        n = F.dismiss_dialogs(app)
        print("dismissed", n, flush=True)
        shot("after_dismiss")
        state(app, "after_dismiss")
        time.sleep(10)
        shot("after_10s")
        state(app, "after_10s")
print("done", flush=True)
