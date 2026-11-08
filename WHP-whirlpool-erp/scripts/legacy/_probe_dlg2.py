# -*- coding: utf-8 -*-
"""临时探针：启动 javaws 后抓 Java 弹窗（pywinauto 截图），打印文案并自动点。"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_jws
import win32gui
from pywinauto import Desktop, mouse
from erp_flow_org import ocr_hits

LOGS = erp_jws.LOGS

op, _j, home = erp_jws.login()
_p, params, jars = erp_jws.fetch_applet(op)
jp = erp_jws.build_jnlp(params, jars, os.path.join(LOGS, "ebs_forms_probe.jnlp"))
exe = erp_jws.find_javaws()
subprocess.Popen([exe, jp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
print("launched", flush=True)

seen = set()
for i in range(40):
    time.sleep(2)
    cands = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        cls = win32gui.GetClassName(h)
        t = win32gui.GetWindowText(h) or ""
        if cls in ("#32770", "SunAwtDialog", "SunAwtFrame") and t and "SKILLS" not in t:
            cands.append((h, cls, t[:60]))

    win32gui.EnumWindows(cb, None)
    for h, cls, t in cands:
        if h in seen:
            continue
        seen.add(h)
        print(f"\n=== [{i * 2}s] {h} {cls} {t}", flush=True)
        try:
            w = Desktop(backend="win32").window(handle=h)
            img = w.capture_as_image()
            img.save(os.path.join(LOGS, f"dlgcap_{h}.png"))
            print("   img", img.size, flush=True)
            toks = list(ocr_hits(img))
            for tx, sc, r in toks:
                print("   ", round(sc, 2), repr(tx), (r.x, r.y, r.w, r.h), flush=True)
            l, tp = win32gui.GetWindowRect(h)[:2]
            for kw in ("我接受风险", "运行", "稍后", "以后", "继续", "确定"):
                hit = [r for tx, sc, r in toks if kw in tx.replace(" ", "")]
                if hit:
                    r = hit[0]
                    cx, cy = l + r.x + r.w // 2, tp + r.y + r.h // 2
                    print(f"   -> click {kw!r} ({cx},{cy})", flush=True)
                    win32gui.SetForegroundWindow(h)
                    time.sleep(0.3)
                    mouse.click(button="left", coords=(cx, cy))
                    time.sleep(0.8)
                    break
        except Exception as e:
            print("   fail", e, flush=True)
