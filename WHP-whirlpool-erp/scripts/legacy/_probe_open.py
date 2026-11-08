# -*- coding: utf-8 -*-
"""临时探针：观察 IE 打开 Forms 地址后到底发生了什么（不要交付）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ie11
import erp_navigator
import win32gui
from PIL import ImageGrab

LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"
RESP = "PO,SANYO合肥三洋物料计划员"


def shot(tag):
    p = os.path.join(LOGS, f"probe_open_{tag}.png")
    ImageGrab.grab().save(p)
    print("shot", p, flush=True)


def frames():
    out = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "IEFrame":
            out.append(h)
        return True

    win32gui.EnumWindows(cb, None)
    return out


ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
print("login", ie is not None and erp_ie11.is_logged_in(ie), flush=True)
ok = erp_navigator.expand_responsibility(ie, RESP)
print("expand", ok, flush=True)
url = erp_navigator.read_function_url(ie, "更改组织", resp_name=RESP)
print("url", url[:120] if url else None, flush=True)
before = erp_navigator.snapshot_forms_windows()
print("frames before", frames(), "applets before", before, flush=True)
ie2 = erp_navigator.open_forms_window(url)
print("dispatched", ie2 is not None, flush=True)
for i in range(12):
    time.sleep(10)
    try:
        hw = ie2.HWND
    except Exception as e:
        hw = f"ERR {e}"
    try:
        loc = ie2.LocationURL
    except Exception as e:
        loc = f"ERR {e}"
    print(f"[{10 * (i + 1)}s] hwnd={hw} loc={str(loc)[:80]}", flush=True)
    print(f"   frames={frames()} applets={erp_navigator.snapshot_forms_windows()}",
          flush=True)
    shot(i)
    if i == 3:
        break
print("done", flush=True)
