# -*- coding: utf-8 -*-
"""临时探针：无 -verbose 启动 javaws，逐帧观察 + 捕获任何 #32770 弹窗文案。"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_forms
import erp_jws
import erp_navigator
import erp_ui
from erp_flow_org import ocr_hits

LOGS = erp_jws.LOGS
import win32gui
from PIL import ImageGrab


def dialogs():
    out = []
    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        cls = win32gui.GetClassName(h)
        t = win32gui.GetWindowText(h) or ""
        if cls == "#32770" and t:
            out.append((h, t[:60]))
    win32gui.EnumWindows(cb, None)
    return out


def dump(h, tag):
    try:
        l, top, r, b = win32gui.GetWindowRect(h)
        img = ImageGrab.grab(bbox=(l, top, r, b), all_screens=True)
        img.save(os.path.join(LOGS, f"dlg_{tag}.png"))
        texts = [t for t, s, rr in ocr_hits(img)]
        print(f"  [DLG {tag}] {' / '.join(texts)[:300]}", flush=True)
    except Exception as e:
        print("  dump fail", e, flush=True)


op, _jar, home = erp_jws.login()
_page, params, jars = erp_jws.fetch_applet(op)
jp = erp_jws.build_jnlp(params, jars, os.path.join(LOGS, "ebs_forms_probe.jnlp"))
exe = erp_jws.find_javaws()
_f = open(os.path.join(LOGS, "javaws_out.txt"), "wb")
proc = subprocess.Popen([exe, jp], stdout=_f, stderr=subprocess.STDOUT)
print("pid", proc.pid, flush=True)

before = set(erp_navigator.snapshot_forms_windows())
t0 = time.time()
n = 0
for i in range(48):
    time.sleep(5)
    el = int(time.time() - t0)
    erp_jws.accept_security_warning(save_png=os.path.join(LOGS, "jws_secwarn.png"))
    for h, t in dialogs():
        dump(h, f"{el}s")
    snap = erp_navigator.snapshot_forms_windows()
    txt = ""
    for h in snap:
        if h in before:
            continue
        app = erp_forms.FormsApp()
        if not app.connect_by_hwnd(h):
            continue
        img = erp_ui.capture(app, focus=True)
        if img is None:
            continue
        if n < 4:
            img.save(os.path.join(LOGS, f"probe_v2_{el}s.png"))
            n += 1
        txt = " | ".join(t for t, s, r in ocr_hits(img))[:200]
    print(f"[{el:3d}s] alive={proc.poll() is None} win={list(snap)} txt={txt}", flush=True)
    if "更改组织" in txt:
        print("=== 表单已就绪 ===", flush=True)
        break
    if i % 6 == 5:
        ImageGrab.grab(all_screens=True).save(os.path.join(LOGS, f"scr_{el}s.png"))
