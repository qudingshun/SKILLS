# -*- coding: utf-8 -*-
"""临时探针：找到 Java 弹窗（#32770），用 pywinauto 截图 + OCR，打印按钮文案。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win32gui
from pywinauto import Application
from erp_flow_org import ocr_hits

LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"

cands = []


def cb(h, _):
    if not win32gui.IsWindowVisible(h):
        return
    cls = win32gui.GetClassName(h)
    t = win32gui.GetWindowText(h) or ""
    if cls in ("#32770", "SunAwtDialog") and t:
        cands.append((h, cls, t[:70]))


win32gui.EnumWindows(cb, None)
print("cands:", cands, flush=True)

for h, cls, t in cands:
    try:
        a = Application(backend="win32").connect(handle=h)
        img = a.window.capture_as_image()
        p = os.path.join(LOGS, f"dlgcap_{h}.png")
        img.save(p)
        print(f"--- {h} {cls} {t} img={img.size} -> {p}")
        for tx, sc, r in ocr_hits(img):
            print("   ", round(sc, 2), repr(tx), (r.x, r.y, r.w, r.h))
    except Exception as e:
        print("fail", h, e)
