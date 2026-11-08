# -*- coding: utf-8 -*-
"""临时探针：绕开 javaws，用 JRE 自带的 sun.applet.AppletViewer 直接跑 Forms applet，
把 JVM 自己的 stdout/stderr 抓到文件里 —— 卡在 ORACLE 启动图时，异常信息只在这里。
"""
import html
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_jws

LOGS = erp_jws.LOGS
JAVA = r"C:\Program Files (x86)\Java\jre1.8.0_191\bin\java.exe"


def build_html(params, jars, path):
    arc = ",".join(dict.fromkeys(jars))          # fndlist.jar 在 JNLP 里出现两次
    body = [
        "<html><body>",
        '<applet code="oracle.apps.fnd.formsClient.FormsLauncher"',
        f'        archive="{html.escape(arc, quote=True)}"',
        f'        codebase="{erp_jws.BASE}/"',
        '        width="995" height="700" name="FormsApplet">',
    ]
    for k, v in params:
        body.append(f'<param name="{k}" value="{html.escape(v, quote=True)}">')
    body += ["</applet>", "</body></html>"]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body))
    return path


if __name__ == "__main__":
    op, _jar, home = erp_jws.login()
    _page, params, jars = erp_jws.fetch_applet(op)
    print(f"参数 {len(params)} 个 / jar {len(jars)} 个", flush=True)
    jp = os.path.join(LOGS, "applet_viewer.html")
    build_html(params, jars, jp)

    ov = erp_jws.ensure_security_override()
    cmd = [JAVA, f"-Djava.security.properties={ov}", "sun.applet.AppletViewer", jp]
    print(" ".join(cmd), flush=True)
    outp = os.path.join(LOGS, "applet_viewer.out")
    with open(outp, "wb") as f:
        p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT)
        try:
            p.wait(timeout=200)
        except subprocess.TimeoutExpired:
            print("200s 未退出，kill", flush=True)
            p.kill()
    with open(outp, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "gbk"):
        try:
            print(raw.decode(enc, "replace"), flush=True)
            break
        except Exception:
            continue
