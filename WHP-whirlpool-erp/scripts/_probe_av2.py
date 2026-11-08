# -*- coding: utf-8 -*-
"""临时探针：只重跑 AppletViewer（参数从已有 JNLP 里读，不重新登录），快速迭代 HTML 格式。"""
import html
import os
import re
import subprocess
import sys

LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"
JAVA = r"C:\Program Files (x86)\Java\jre1.8.0_191\bin\java.exe"
OV = os.path.join(LOGS, "java.security.override")

jnlp = open(os.path.join(LOGS, "ebs_forms.jnlp"), encoding="utf-8").read()
codebase = re.search(r'codebase="([^"]+)"', jnlp).group(1)
jars = re.findall(r'<jar href="([^"]+)"', jnlp)
params = re.findall(r'<param name="([^"]+)"\s+value="([^"]*)"', jnlp)
main = re.search(r'main-class="([^"]+)"', jnlp).group(1)
print(f"{len(params)} params / {len(jars)} jars / main={main} / codebase={codebase}", flush=True)

uniq = list(dict.fromkeys(jars))

# AppletViewer 用的是 JDK 自带的老 HTML 解析器：必须全部加引号，且一个标签一行
lines = ["<html><body>"]
attrs = [
    f'code="{main}"',
    f'codebase="{codebase}"',
    f'archive="{",".join(uniq)}"',
    'width="995"', 'height="700"',
]
lines.append("<applet " + " ".join(attrs) + ">")
for k, v in params:
    lines.append(f'<param name="{k}" value="{html.escape(v, quote=True)}">')
lines += ["</applet>", "</body></html>"]

path = os.path.join(LOGS, "applet_viewer.html")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(open(path, encoding="utf-8").read()[:600], flush=True)

outp = os.path.join(LOGS, "applet_viewer.out")
with open(outp, "wb") as f:
    p = subprocess.Popen([JAVA, f"-Djava.security.properties={OV}",
                          "sun.applet.AppletViewer", path],
                         stdout=f, stderr=subprocess.STDOUT)
    try:
        p.wait(timeout=150)
    except subprocess.TimeoutExpired:
        print("150s 未退出 → kill", flush=True)
        p.kill()

raw = open(outp, "rb").read()
print("=" * 20, "OUTPUT", "=" * 20, flush=True)
print(raw.decode("gbk", "replace"), flush=True)
