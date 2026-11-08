# -*- coding: utf-8 -*-
"""临时探针：打开 Java 控制台（deployment.console.startup.mode=SHOW），
把 applet 自己抛的异常抓出来看 —— 它卡在 ORACLE 启动图，控制台里通常有真相。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_jws
import win32gui
from pywinauto import Desktop
from erp_flow_org import ocr_hits

LOGS = erp_jws.LOGS
outp = os.path.join(LOGS, "console_dump.txt")


def wins():
    res = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        cls = win32gui.GetClassName(h)
        t = win32gui.GetWindowText(h) or ""
        if not t:
            return
        res.append((h, cls, t))
    win32gui.EnumWindows(cb, None)
    return res


def is_console(cls, t):
    low = t.lower()
    return ("console" in low or "控制台" in t) and "web start" not in low


if __name__ == "__main__":
    op, _jar, home = erp_jws.login()
    _page, params, jars = erp_jws.fetch_applet(op)
    jp = erp_jws.build_jnlp(params, jars, os.path.join(LOGS, "ebs_forms_console.jnlp"))
    erp_jws.launch(jp)

    seen_txt = set()
    f = open(outp, "w", encoding="utf-8")
    try:
        for i in range(60):
            time.sleep(4)
            erp_jws.accept_security_warning()
            for h, cls, t in wins():
                if not is_console(cls, t):
                    continue
                try:
                    img = Desktop(backend="win32").window(handle=h).capture_as_image()
                except Exception as e:
                    print(f"[{i*4}s] cap fail {e}", flush=True)
                    continue
                img.save(os.path.join(LOGS, f"console_{i*4}s.png"))
                toks = [x for x, s, r in ocr_hits(img)]
                line = " | ".join(toks)
                print(f"[{i*4}s] CONSOLE {h} {t} :: {line[:400]}", flush=True)
                f.write(f"[{i*4}s]\n{line}\n")
                f.flush()
            # 也报一下 applet 窗口状态
            ap = [x for x in wins() if x[1] == "SunAwtFrame" and "Oracle" in x[2]]
            if i % 5 == 0:
                print(f"[{i*4}s] applet={ap}", flush=True)
    finally:
        f.close()
