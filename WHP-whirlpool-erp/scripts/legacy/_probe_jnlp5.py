# -*- coding: utf-8 -*-
"""临时探针 10：登录 → MAINMENUREST(职责菜单) → 找「更改组织」RF.jsp URL → 抓 applet HTML（不要交付）。"""
import http.cookiejar
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erp_common import ERP_USERNAME, get_erp_password  # noqa: E402

LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"
BASE = "https://erp.whirlpool-china.com:4446"
LOGIN_URL = BASE + "/OA_HTML/AppsLogin"

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
ctx.minimum_version = ssl.TLSVersion.TLSv1
ctx.set_ciphers("DEFAULT@SECLEVEL=0")
ctx.options |= 0x40000

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar),
    urllib.request.HTTPSHandler(context=ctx),
)
opener.addheaders = [
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko"),
    ("Accept-Language", "zh-CN"),
]


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
    html, final = get(LOGIN_URL)
    action = urllib.parse.urljoin(
        final, re.search(r'<form[^>]*action="([^"]+)"', html, re.I).group(1).replace("&amp;", "&"))
    d = {}
    for mm in re.finditer(r"<input[^>]*>", html, re.I):
        tag = mm.group(0)
        if "hidden" not in tag.lower():
            continue
        nm = re.search(r'name="([^"]+)"', tag)
        vl = re.search(r'value="([^"]*)"', tag)
        if nm:
            d[nm.group(1)] = vl.group(1) if vl else ""
    tok = re.search(r"_FORM_SUBMIT_BUTTON':'([^']+)'", html)
    if tok:
        d["_FORM_SUBMIT_BUTTON"] = tok.group(1)
    d.pop("Cancel$$unvalidated", None)
    d["usernameField"] = ERP_USERNAME
    d["passwordField"] = get_erp_password()
    return post(action, list(d.items()))


html, final = login()
print("login ->", final[:80], len(html), flush=True)

menu_url = BASE + "/OA_HTML/RF.jsp?function_id=MAINMENUREST&security_group_id=0"
menu, mfinal = get(menu_url)
open(os.path.join(LOGS, "menu_rest.txt"), "w", encoding="utf-8").write(menu)
print("menu ->", mfinal[:80], len(menu), flush=True)
print("has 更改组织:", "更改组织" in menu, flush=True)
print(menu[:600], flush=True)

# 菜单里每项形如 launchForm('...RF.jsp?function_id=...&resp_id=...')
cands = re.findall(r"RF\.jsp\?function_id=\d+[^'\"]*", menu)
print("rf candidates:", len(cands), flush=True)
for c in cands[:10]:
    print("  ", c[:170], flush=True)

i = menu.find("更改组织")
print("---- ctx around 更改组织 ----", flush=True)
print(menu[max(0, i - 800): i + 400], flush=True)
