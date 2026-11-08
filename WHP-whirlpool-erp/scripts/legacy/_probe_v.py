# -*- coding: utf-8 -*-
"""临时探针：javaws -verbose 冷启动观察（cache 已清空），看它为什么起来又退出。"""
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

op, _jar, home = erp_jws.login()
_page, params, jars = erp_jws.fetch_applet(op)
jp = erp_jws.build_jnlp(params, jars, os.path.join(LOGS, "ebs_forms_probe.jnlp"))
print("jnlp ok", flush=True)

exe = erp_jws.find_javaws()
out = open(os.path.join(LOGS, "javaws_verbose.txt"), "wb")
proc = subprocess.Popen([exe, "-verbose", jp], stdout=out, stderr=subprocess.STDOUT)
print("pid", proc.pid, flush=True)

before = set(erp_navigator.snapshot_forms_windows())
t0 = time.time()
shot_done = set()
for i in range(55):
    time.sleep(4)
    el = int(time.time() - t0)
    erp_jws.accept_security_warning(save_png=os.path.join(LOGS, "jws_secwarn.png"))
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
        if h not in shot_done:
            img.save(os.path.join(LOGS, f"probe_js_{el}s.png"))
            shot_done.add(h)
        txt = " | ".join(t for t, s, r in ocr_hits(img))[:160]
    print(f"[{el:3d}s] alive={proc.poll() is None} win={list(snap)} txt={txt}", flush=True)
    if "更改组织" in txt:
        print("=== 表单已就绪 ===", flush=True)
        break
    if proc.poll() is not None and not snap:
        print("=== javaws 已退出且无窗口 ===", flush=True)
        break
out.close()
