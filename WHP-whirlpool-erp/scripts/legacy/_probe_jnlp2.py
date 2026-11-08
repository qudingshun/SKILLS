# -*- coding: utf-8 -*-
"""临时探针 7：复用已登录 EBS 会话（WinINet 共享 IE cookie）抓 RF.jsp 真实 HTML，
   找 forms/frmservlet 与 JNLP 地址。不启动浏览器窗口。（不要交付）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ie11
import erp_navigator
import win32inet

LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"
RESP = "PO,SANYO合肥三洋物料计划员"
UA = "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko"


def fetch(url, flags=0):
    """用 WinINet（与 IE 共享 cookie 罐）取页面。"""
    sess = win32inet.InternetOpen(UA, 0, None, None, 0)
    try:
        h = win32inet.InternetOpenUrl(sess, url, None, flags, 0)
        chunks = []
        while True:
            try:
                buf = win32inet.InternetReadFile(h, 8192)
            except Exception:
                break
            if not buf:
                break
            chunks.append(buf)
        data = b"".join(chunks)
        return data
    finally:
        try:
            win32inet.InternetCloseHandle(sess)
        except Exception:
            pass


hit = erp_ie11.find_logged_in_ie()
print("logged_in_ie:", None if not hit else (hit[1], hit[2][:70]), flush=True)
if not hit:
    sys.exit("没有可复用的已登录窗口")
ie = hit[0]

print("expand:", erp_navigator.expand_responsibility(ie, RESP), flush=True)
url = erp_navigator.read_function_url(ie, "更改组织", resp_name=RESP)
print("rf url:", (url or "")[:160], flush=True)
if not url:
    sys.exit("拿不到更改组织 URL")

raw = fetch(url)
print("bytes:", len(raw), flush=True)
for enc in ("utf-8", "gbk", "latin-1"):
    try:
        html = raw.decode(enc)
        if "applet" in html.lower() or "jnlp" in html.lower():
            print("decoded with", enc, flush=True)
            break
    except Exception:
        continue
else:
    html = raw.decode("latin-1")
open(os.path.join(LOGS, "jnlp_rf.html"), "w", encoding="utf-8").write(html)

for kw in ("applet", "jnlp", "frmservlet", "codebase", "archive", "FormsClient"):
    idx = [m.start() for m in re.finditer(kw, html, re.I)]
    print(f"  {kw}: {len(idx)}", flush=True)

for m in re.finditer(r"https?://[^\"'\s>]{0,240}(?:frmservlet|jnlp|\.jar)[^\"'\s>]{0,120}",
                     html, re.I):
    print("URL>", m.group(0)[:240], flush=True)

# 打印 applet 标签附近内容
i = html.lower().find("<applet")
if i < 0:
    i = html.lower().find("jnlp")
print("---- context ----", flush=True)
print(html[max(0, i - 400): i + 1600], flush=True)
