# -*- coding: utf-8 -*-
"""临时探针：Edge(IE模式) 桌面截图 + OCR 定位登录框，登录后开 RF.jsp 找 applet。"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win32gui
from PIL import ImageGrab
from pywinauto import keyboard, mouse
from erp_common import ERP_USERNAME, get_erp_password
from erp_flow_org import ocr_hits
import erp_jws
import erp_navigator

LOGS = erp_jws.LOGS
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
RF = (erp_jws.BASE + "/OA_HTML/RF.jsp?function_id=261&resp_id=51318"
      "&resp_appl_id=201&security_group_id=0&lang_code=ZHS")


def find_edge():
    out = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        if win32gui.GetClassName(h) != "Chrome_WidgetWin_1":
            return
        t = win32gui.GetWindowText(h) or ""
        if t and t != "SKILLS":
            out.append((h, t))
    win32gui.EnumWindows(cb, None)
    for h, t in out:
        if "Microsoft" in t and "Edge" in t:
            return h, t
    return (out[0] if out else (None, None))


def shot(h):
    """窗矩形 + 桌面 BitBlt 截图（Chromium 的 capture_as_image 常拿不到页面内容）。"""
    l, t, r, b = win32gui.GetWindowRect(h)
    img = ImageGrab.grab(bbox=(l, t, r, b))
    return img, (l, t)


subprocess.Popen([EDGE, "--new-window", erp_jws.LOGIN_URL])
time.sleep(9)
h, title = find_edge()
print("edge", h, title, flush=True)
if h is None:
    sys.exit("无 Edge 窗口")

img, (L, T) = shot(h)
img.save(os.path.join(LOGS, "edge_page.png"))
print("win img", img.size, "origin", L, T, flush=True)
toks = list(ocr_hits(img))
for tx, sc, r in toks:
    print("   ", round(sc, 2), repr(tx), (r.x, r.y, r.w, r.h), flush=True)

u = next((r for tx, sc, r in toks if "用户" in tx), None)
p = next((r for tx, sc, r in toks if "口令" in tx or "密码" in tx), None)
print("user label", u, "pwd label", p, flush=True)
if u is None or p is None:
    sys.exit("没定位到输入框")

win32gui.SetForegroundWindow(h)
time.sleep(0.5)
mouse.click(button="left", coords=(L + u.x + u.w + 120, T + u.y + u.h // 2))
time.sleep(0.4)
keyboard.send_keys(ERP_USERNAME)
time.sleep(0.4)
mouse.click(button="left", coords=(L + p.x + p.w + 120, T + p.y + p.h // 2))
time.sleep(0.4)
keyboard.send_keys(get_erp_password())
time.sleep(0.4)
keyboard.send_keys("{ENTER}")
print("submitted", flush=True)
time.sleep(10)

img, _o = shot(h)
img.save(os.path.join(LOGS, "edge_after_login.png"))
toks = list(ocr_hits(img))
txt = " | ".join(tx for tx, sc, r in toks)
print("after login:", txt[:220], flush=True)

win32gui.SetForegroundWindow(h)
time.sleep(0.4)
keyboard.send_keys("^l")
time.sleep(0.4)
keyboard.send_keys(RF)
keyboard.send_keys("{ENTER}")
print("go RF.jsp", flush=True)

before = set(erp_navigator.snapshot_forms_windows())
for i in range(20):
    time.sleep(6)
    snap = erp_navigator.snapshot_forms_windows()
    img, _o = shot(h)
    txt = " | ".join(tx for tx, sc, r in ocr_hits(img))[:150]
    print(f"[{(i + 1) * 6}s] applet={[x for x in snap if x not in before]} page={txt}", flush=True)
    if "更改组织" in txt or "常用表单" in txt:
        img.save(os.path.join(LOGS, "edge_applet_ok.png"))
        print("=== APPOK ===", flush=True)
        break
