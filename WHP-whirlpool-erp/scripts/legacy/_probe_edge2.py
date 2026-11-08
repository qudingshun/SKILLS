# -*- coding: utf-8 -*-
"""临时探针：Edge(IE 模式) 里登录 EBS → 打开 RF.jsp → 看 applet 是否真的跑起来。"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win32gui
from pywinauto import Desktop, mouse
from erp_common import ERP_USERNAME, get_erp_password
from erp_flow_org import ocr_hits
import erp_navigator
import erp_jws

LOGS = erp_jws.LOGS
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

RF = (erp_jws.BASE + "/OA_HTML/RF.jsp?function_id=261&resp_id=51318"
      "&resp_appl_id=201&security_group_id=0&lang_code=ZHS")


def edge_win():
    out = []
    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        cls = win32gui.GetClassName(h)
        t = win32gui.GetWindowText(h) or ""
        if cls == "Chrome_WidgetWin_1" and t and t != "SKILLS":
            out.append((h, t))
    win32gui.EnumWindows(cb, None)
    for h, t in out:
        if any(k in t for k in ("Oracle", "登录", "ERP", "惠而浦", "Microsoft​ Edge")):
            return h, t
    return (out[0] if out else (None, None))


def shot_and_ocr(h):
    w = Desktop(backend="win32").window(handle=h)
    img = w.capture_as_image()
    return img, list(ocr_hits(img))


def click_tok(h, tok, dx=0.0, dy=0.5):
    l, t = win32gui.GetWindowRect(h)[:2]
    cx = l + tok.x + int(tok.w * dx) + (tok.w // 2 if dx == 0 else 0)
    cy = t + tok.y + int(tok.h * dy)
    win32gui.SetForegroundWindow(h)
    time.sleep(0.3)
    mouse.click(button="left", coords=(cx, cy))
    time.sleep(0.5)


subprocess.Popen([EDGE, "--new-window", erp_jws.LOGIN_URL])
time.sleep(8)
h, title = edge_win()
print("edge:", h, title, flush=True)
if h is None:
    sys.exit("没有 Edge 窗口")

img, toks = shot_and_ocr(h)
print("page:", " | ".join(t for t, s, r in toks)[:200], flush=True)

# 找用户名/口令字段
u = next((r for t, s, r in toks if "用户" in t), None)
p = next((r for t, s, r in toks if "口令" in t or "密码" in t), None)
print("user field label", u, "pwd label", p, flush=True)

if u is not None:
    click_tok(h, u, dx=1.3)
    win32gui.SetForegroundWindow(h)
    from pywinauto import keyboard
    keyboard.send_keys(ERP_USERNAME, with_spaces=True)
    time.sleep(0.5)
if p is not None:
    click_tok(h, p, dx=1.3)
    from pywinauto import keyboard
    keyboard.send_keys(get_erp_password(), with_spaces=True)
    time.sleep(0.5)
    keyboard.send_keys("{ENTER}")
    time.sleep(8)

img, toks = shot_and_ocr(h)
print("after login:", " | ".join(t for t, s, r in toks)[:200], flush=True)
img.save(os.path.join(LOGS, "edge_after_login.png"))

# 直接开 RF.jsp
win32gui.SetForegroundWindow(h)
time.sleep(0.4)
from pywinauto import keyboard
keyboard.send_keys("^l")
time.sleep(0.5)
keyboard.send_keys(RF, with_spaces=True)
keyboard.send_keys("{ENTER}")
print("go RF.jsp", flush=True)

before = set(erp_navigator.snapshot_forms_windows())
for i in range(30):
    time.sleep(6)
    snap = erp_navigator.snapshot_forms_windows()
    new = [x for x in snap if x not in before]
    img, toks = shot_and_ocr(h)
    txt = " | ".join(t for t, s, r in toks)[:160]
    print(f"[{(i + 1) * 6}s] applet={new} page={txt}", flush=True)
    if "更改组织" in txt or "常用表单" in txt:
        img.save(os.path.join(LOGS, "edge_applet_ok.png"))
        print("=== Edge 里 applet 起来了 ===", flush=True)
        break
