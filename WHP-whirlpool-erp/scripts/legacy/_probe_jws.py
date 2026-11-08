# -*- coding: utf-8 -*-
"""临时探针 13：HTTP 登录 → RF.jsp 取 applet 参数 → 生成 JNLP → javaws 起 applet（不要交付）。

目的：验证「不经浏览器、用 Java Web Start 直接起 Oracle Forms applet」是否可行。
"""
import html as htmlmod
import http.cookiejar
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erp_common import ERP_USERNAME, get_erp_password  # noqa: E402

BASE = "https://erp.whirlpool-china.com:4446"
LOGIN_URL = BASE + "/OA_HTML/AppsLogin"
LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"
JAVAWS = r"C:\Program Files (x86)\Java\jre1.8.0_191\bin\javaws.exe"

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
ctx.minimum_version = ssl.TLSVersion.TLSv1
ctx.set_ciphers("DEFAULT@SECLEVEL=0")
ctx.options |= 0x40000
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar),
    urllib.request.HTTPSHandler(context=ctx))
opener.addheaders = [
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko"),
    ("Accept-Language", "zh-CN")]


def dec(raw):
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            s = raw.decode(enc)
        except Exception:
            continue
        if enc != "latin-1" and not re.search(r"[\u4e00-\u9fff]", s):
            continue
        return s
    return raw.decode("latin-1", "replace")


def get(url):
    with opener.open(url, timeout=60) as r:
        return dec(r.read()), r.geturl()


def post(url, pairs):
    body = urllib.parse.urlencode(pairs, encoding="gbk").encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with opener.open(req, timeout=90) as r:
        return dec(r.read()), r.geturl()


def login():
    page, final = get(LOGIN_URL)
    action = urllib.parse.urljoin(
        final, re.search(r'<form[^>]*action="([^"]+)"', page, re.I).group(1).replace("&amp;", "&"))
    d = {}
    for mm in re.finditer(r"<input[^>]*>", page, re.I):
        tag = mm.group(0)
        if "hidden" not in tag.lower():
            continue
        nm = re.search(r'name="([^"]+)"', tag)
        vl = re.search(r'value="([^"]*)"', tag)
        if nm:
            d[nm.group(1)] = vl.group(1) if vl else ""
    tok = re.search(r"_FORM_SUBMIT_BUTTON':'([^']+)'", page)
    if tok:
        d["_FORM_SUBMIT_BUTTON"] = tok.group(1)
    d.pop("Cancel$$unvalidated", None)
    d["usernameField"] = ERP_USERNAME
    d["passwordField"] = get_erp_password()
    return post(action, list(d.items()))


RF = ("{base}/OA_HTML/RF.jsp?function_id={fid}&resp_id={rid}"
      "&resp_appl_id={aid}&security_group_id=0&lang_code=ZHS")
IDS = {"fid": 261, "rid": 51318, "aid": 201}

page, final = login()
print("login ok:", final[:60], flush=True)
rf_url = RF.format(base=BASE, **IDS)
page, final = get(rf_url)
print("RF page:", len(page), flush=True)
open(os.path.join(LOGS, "rf_current.html"), "w", encoding="utf-8").write(page)

i = page.lower().find("<applet")
if i < 0:
    sys.exit("RF 页面里没有 applet 标签")
applet_html = page[i:]
end = applet_html.lower().find("</applet>")
applet_html = applet_html[: end + 9] if end > 0 else applet_html[:6000]

params = []
for m in re.finditer(r"<PARAM\s+name=(\"?)([A-Za-z0-9_]+)\1\s+value=(\")(.*?)\3\s*>",
                     applet_html, re.I | re.S):
    name, value = m.group(2), htmlmod.unescape(m.group(4))
    if name:
        params.append((name, value))
print("params:", len(params), [p[0] for p in params][:8], flush=True)

arcs = re.search(r'archive=(\"[^\"]*\")', applet_html, re.I)
jars = []
if arcs:
    jars = [a.strip().lstrip("/") for a in arcs.group(1).strip('"').split(",") if a.strip()]

jsec = ['        <jar href="%s" download="eager" main="false"/>' % j for j in jars]
par = ['        <param name="%s" value="%s"/>' % (
    n, htmlmod.escape(v, quote=True)) for n, v in params]
jnlp = f"""<?xml version="1.0" encoding="UTF-8"?>
<jnlp spec="1.0+" codebase="{BASE}/">
    <information>
        <title>Oracle Applications</title>
        <vendor>Oracle</vendor>
    </information>
    <security>
        <all-permissions/>
    </security>
    <resources>
        <j2se version="1.8+"/>
{chr(10).join(jsec)}
    </resources>
    <applet-desc main-class="oracle.apps.fnd.formsClient.FormsLauncher"
                 name="FormsApplet" width="995" height="700">
{chr(10).join(par)}
    </applet-desc>
</jnlp>
"""
jp = os.path.join(LOGS, "ebs_forms.jnlp")
open(jp, "w", encoding="utf-8").write(jnlp)
print("JNLP written:", jp, len(jnlp), flush=True)
print("jars:", len(jars), flush=True)

proc = subprocess.Popen([JAVAWS, jp])
print("javaws pid", proc.pid, flush=True)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_navigator  # noqa: E402

for i in range(24):
    time.sleep(5)
    snap = erp_navigator.snapshot_forms_windows()
    print(f"[{(i + 1) * 5}s] applets={snap}", flush=True)
    if snap:
        break
print("javaws alive:", proc.poll() is None, flush=True)
