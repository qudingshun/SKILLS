# -*- coding: utf-8 -*-
"""临时探针 14：javaws 启动过程逐帧观察（不交付）。"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_jws
import erp_forms
import erp_navigator
import erp_ui
from erp_flow_org import ocr_hits

LOGS = erp_jws.LOGS

op, _jar, home = erp_jws.login()
_page, params, jars = erp_jws.fetch_applet(op)
jp = erp_jws.build_jnlp(params, jars, os.path.join(LOGS, "ebs_forms_probe.jnlp"))
print("jnlp", jp, flush=True)

exe = erp_jws.find_javaws()
out = open(os.path.join(LOGS, "javaws_verbose.txt"), "wb")
proc = subprocess.Popen([exe, "-verbose", jp], stdout=out, stderr=subprocess.STDOUT)
print("pid", proc.pid, flush=True)

before = set(erp_navigator.snapshot_forms_windows())
t0 = time.time()
seen = set()
for i in range(40):
    time.sleep(4)
    el = int(time.time() - t0)
    if erp_jws.find_security_warning():
        print(f"[{el}s] 安全警告出现 -> 自动确认", flush=True)
        erp_jws.accept_security_warning()
    snap = erp_navigator.snapshot_forms_windows()
    txt = ""
    target = None
    for h in snap:
        if h in before:
            continue
        app = erp_forms.FormsApp()
        if not app.connect_by_hwnd(h):
            continue
        target = h
        img = erp_ui.capture(app, focus=True)
        if img is None:
            txt = "<no img>"
            continue
        if h not in seen:
            img.save(os.path.join(LOGS, f"probe_jws_{el}s.png"))
            seen.add(h)
        hs = ocr_hits(img)
        txt = " | ".join(t for t, s, r in hs)[:200]
    alive = proc.poll() is None
    print(f"[{el}s] snap={list(snap)} alive={alive} txt={txt}", flush=True)
    if txt and "更改组织" in txt:
        print("=== 表单已就绪 ===", flush=True)
        break
print("final proc rc", proc.poll(), flush=True)
out.close()
