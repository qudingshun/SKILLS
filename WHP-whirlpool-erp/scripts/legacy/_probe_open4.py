# -*- coding: utf-8 -*-
"""临时探针 4：IE 进程/窗口存活跟踪（不要交付）。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ie11
import erp_navigator
import psutil
import win32gui
import win32process

RESP = "PO,SANYO合肥三洋物料计划员"


def ie_procs():
    out = []
    for p in psutil.process_iter(["pid", "name", "create_time"]):
        if (p.info["name"] or "").lower() == "iexplore.exe":
            out.append(p.info["pid"])
    return out


def windows_of(pids):
    out = []

    def cb(h, _):
        try:
            if win32gui.GetClassName(h) != "IEFrame":
                return True
            pid = win32process.GetWindowThreadProcessId(h)[1]
            if pid in pids:
                out.append((h, win32gui.IsWindowVisible(h), win32gui.IsIconic(h),
                            win32gui.GetWindowRect(h),
                            win32gui.GetWindowText(h)[:40]))
        except Exception:
            pass
        return True

    win32gui.EnumWindows(cb, None)
    return out


ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
print("login", ie is not None and erp_ie11.is_logged_in(ie), flush=True)
print("procs", ie_procs(), "wins", windows_of(ie_procs()), flush=True)
erp_navigator.expand_responsibility(ie, RESP)
url = erp_navigator.read_function_url(ie, "更改组织", resp_name=RESP)
print("url ok", bool(url), flush=True)
ie2 = erp_navigator.open_forms_window(url)
print("dispatched", ie2 is not None, flush=True)
for i in range(10):
    time.sleep(6)
    try:
        hw = ie2.HWND
    except Exception as e:
        hw = f"ERR({e.args[0] if e.args else e})"
    pids = ie_procs()
    print(f"[{(i + 1) * 6}s] ie_pids={pids} ie2.HWND={hw}", flush=True)
    print(f"    wins={windows_of(pids)}", flush=True)
    print(f"    applets={erp_navigator.snapshot_forms_windows()}", flush=True)
