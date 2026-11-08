# -*- coding: utf-8 -*-
"""临时探针 12：登录后用已知 function/resp id 直接取 RF.jsp，抓 applet/jnlp_href（不要交付）。"""
import http.cookiejar
import os
import re
import ssl
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erp_common import ERP_USERNAME, get_erp_password  # noqa: E402

BASE = "https://erp.whirlpool-china.com:4446"
LOGIN_URL = BASE + "/OA_HTML/AppsLogin"
LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"

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


home, final = login()
print("login ->", final[:70], len(home), flush=True)
tokens = sorted(set(re.findall(r"oas=([A-Za-z0-9_.\-]+)", home)))

cands = [
    f"{BASE}/OA_HTML/RF.jsp?function_id=261&resp_id=51318&resp_appl_id=201&security_group_id=0&lang_code=ZHS",
]
cands += [cands[0] + "&oas=" + t for t in tokens[:3]]
for u in cands:
    try:
        txt, fu = get(u)
    except Exception as e:
        print("ERR", getattr(e, "code", e), u[-50:], flush=True)
        continue
    has = {k: (k in txt) for k in ("applet", "jnlp", "frmservlet", "更改组织")}
    print(f"[{len(txt):6d}] {has} {fu[:60]}", flush=True)
    if "applet" in txt.lower() or "frmservlet" in txt.lower():
        n = len(os.listdir(LOGS))
        p = os.path.join(LOGS, f"rf_page_{n}.html")
        open(p, "w", encoding="utf-8").write(txt)
        print("SAVED", p, flush=True)
        for m in re.finditer(r'(jnlp_href|archive|codebase)\s*=\s*"([^"]*)"', txt, re.I):
            print("  PARAM", m.group(1), "=", m.group(2)[:200], flush=True)
        break
