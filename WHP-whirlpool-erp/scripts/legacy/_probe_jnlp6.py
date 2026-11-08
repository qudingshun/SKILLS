# -*- coding: utf-8 -*-
"""临时探针 11：主页 oas 令牌逐个试 MAINMENUREST，找能返回菜单的那个（不要交付）。"""
import importlib.util
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "p5", os.path.join(os.path.dirname(os.path.abspath(__file__)), "_probe_jnlp5.py"))
# 直接复用登录逻辑（复制最小实现，避免执行 p5 的后续步骤）
import http.cookiejar
import ssl
import urllib.parse

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
print("tokens", len(tokens), flush=True)

base_menu = BASE + "/OA_HTML/RF.jsp?function_id=MAINMENUREST&security_group_id=0"
tries = [base_menu] + [f"{base_menu}&oas={t}" for t in tokens]
for u in tries:
    try:
        txt, fu = get(u)
        print(f"[{len(txt):6d}] {'更改组织' in txt} {u[-60:]}", flush=True)
        if "更改组织" in txt:
            open(os.path.join(LOGS, "menu_ok.txt"), "w", encoding="utf-8").write(txt)
            print("SAVED menu_ok.txt", flush=True)
            break
    except Exception as e:
        print("ERR", getattr(e, "code", e), u[-60:], flush=True)
