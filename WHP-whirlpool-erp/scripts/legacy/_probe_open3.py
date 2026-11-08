# -*- coding: utf-8 -*-
"""临时探针 3：先规范窗口尺寸(1140x900@0,0)，再看「打开申请」→ 关弹窗 → applet 是否还活（不要交付）。"""
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
    p = os.path.join(F.LOGS, f"po3_{step[0]:02d}_{tag}.png")
    ImageGrab.grab().save(p)
    print(f"[shot] {p}", flush=True)


def state(app, tag):
    img, hits = F.look(app)
    txt = " ".join(t for t, s, r in hits)
    print(f"[state {tag}] n_hits={len(hits)} text[:140]={txt[:140]}", flush=True)
    return img, hits


ie = F.erp_ie11.open_and_login(visible=True, lang="ZHS")
print("login", ie is not None and F.erp_ie11.is_logged_in(ie), flush=True)
print("expand", erp_navigator.expand_responsibility(ie, RESP), flush=True)
url = erp_navigator.read_function_url(ie, "更改组织", resp_name=RESP)
before = erp_navigator.snapshot_forms_windows()
ie2 = erp_navigator.open_forms_window(url)

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

import win32con
import win32gui
win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
win32gui.MoveWindow(hwnd, 0, 0, 1140, 900, True)
time.sleep(2.0)
print("rect after move", win32gui.GetWindowRect(hwnd), flush=True)

app = erp_forms.FormsApp()
print("connect", app.connect_by_hwnd(hwnd), flush=True)
F.force_foreground(hwnd)
erp_ui.focus_window(app, settle=2.0)
img, hits = state(app, "resized")
shot("resized")

row = F.find_tok(hits, F.FACTORY, x_min=100, x_max=320)
print("factory", row, flush=True)
if row:
    F.click_at(app, row[2].center[0], row[2].center[1], F.FACTORY)
    time.sleep(1.0)
    okb = F.find_tok(F.look(app)[1], "确定", y_min=300)
    print("确定", okb, flush=True)
    erp_ui.click_rect(app, okb[2], dx=0.5, dy=0.5)
    time.sleep(2.5)
    shot("after_ok")

item = None
t0 = time.time()
while time.time() - t0 < 40 and item is None:
    img, hits = F.look(app, focus=True)
    for t, s, r in hits:
        if t.strip().lstrip("0123456789.、． ") == F.WORD_APPLY and r.x > 380:
            item = (t, s, r)
    if item is None:
        time.sleep(2.0)
print("2.申请", item, flush=True)
if item:
    erp_ui.click_rect(app, item[2], dx=0.5, dy=0.5)
    time.sleep(0.8)
    btn = F.find_tok(F.look(app)[1], "打开", y_min=450)
    print("打开", btn, flush=True)
    erp_ui.click_rect(app, btn[2], dx=0.5, dy=0.5)
    time.sleep(6.0)
    shot("after_open")
    state(app, "after_open")
    # 只点一次弹窗「确定」，且限定在 applet 画布里
    img, hits = F.look(app)
    cands = [(t, r) for t, s, r in hits
             if t.strip().startswith("确定") and r.x < 1000 and r.y < 800]
    print("dialog 确定 cands", cands, flush=True)
    if cands:
        t, r = cands[0]
        erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
        time.sleep(3.0)
    shot("after_dialog_once")
    state(app, "after_dialog_once")
    time.sleep(8)
    shot("after_8s")
    state(app, "after_8s")
print("done", flush=True)
