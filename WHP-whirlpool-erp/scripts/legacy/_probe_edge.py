# -*- coding: utf-8 -*-
"""临时探针：用 Edge（IE 兼容模式）打开「更改组织」RF.jsp，看 applet 是否真能起来。"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_jws
import win32gui
from PIL import ImageGrab
from erp_flow_org import ocr_hits

LOGS = erp_jws.LOGS
URL = (erp_jws.BASE + "/OA_HTML/RF.jsp?function_id=261&resp_id=51318"
       "&resp_appl_id=201&security_group_id=0&lang_code=ZHS")

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
print("edge:", EDGE, os.path.exists(EDGE))

subprocess.Popen([EDGE, "--new-window", URL])
print("opened", URL[:90], flush=True)

for i in range(24):
    time.sleep(5)
    wins = []
    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        cls = win32gui.GetClassName(h)
        t = win32gui.GetWindowText(h) or ""
        if cls.startswith("Chrome_WidgetWin") and t and ("Oracle" in t or "ERP" in t
                                                        or "登录" in t or "惠而浦" in t):
            wins.append((h, t[:60]))
    win32gui.EnumWindows(cb, None)
    print(f"[{(i + 1) * 5}s] edge_wins={wins}", flush=True)
    if wins:
        h = wins[0][0]
        l, t, r, b = win32gui.GetWindowRect(h)
        img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
        img.save(os.path.join(LOGS, "edge_shot.png"))
        txt = " | ".join(x for x, s, rr in ocr_hits(img))
        print("   OCR:", txt[:300], flush=True)
        if "更改组织" in txt or "常用表单" in txt or "申请" in txt:
            print("=== Edge 里 applet 起来了 ===", flush=True)
            break
