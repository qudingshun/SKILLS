# -*- coding: utf-8 -*-
"""临时探针 8：纯 HTTP 完成 EBS 登录 → 抓 RF.jsp → 找 JNLP（不要交付）。"""
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
        if enc == "latin-1":
            return s
        # 粗判：能解码且出现中文/正常标签
        if re.search(r"[\u4e00-\u9fff]", s) or "<html" in s.lower():
            return s
    return raw.decode("latin-1")


def get(url):
    with opener.open(url, timeout=60) as r:
        return dec(r.read()), r.geturl()


def post(url, pairs):
    body = urllib.parse.urlencode(pairs, encoding="gbk").encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with opener.open(req, timeout=90) as r:
        return dec(r.read()), r.geturl()


html, final = get(LOGIN_URL)
print("login page:", final[:90], len(html), flush=True)
m = re.search(r'<form[^>]*action="([^"]+)"', html, re.I)
action = urllib.parse.urljoin(final, m.group(1).replace("&amp;", "&"))
print("action:", action[:110], flush=True)

fields = []
for mm in re.finditer(r"<input[^>]*>", html, re.I):
    tag = mm.group(0)
    if "hidden" not in tag.lower():
        continue
    nm = re.search(r'name="([^"]+)"', tag)
    vl = re.search(r'value="([^"]*)"', tag)
    if nm:
        fields.append((nm.group(1), vl.group(1) if vl else ""))
print("hidden fields:", len(fields), flush=True)

pwd = get_erp_password()
pairs = list(fields)
pairs += [("usernameField", ERP_USERNAME), ("passwordField", pwd),
          ("SubmitButton", "x")]
html2, final2 = post(action, pairs)
open(os.path.join(LOGS, "jnlp_home2.html"), "w", encoding="utf-8").write(html2)
print("after login:", final2[:110], len(html2), flush=True)
print("logged_in_markers:", {k: (k in html2) for k in ("职责", "主页", "OA.jsp", "口令", "登录")},
      flush=True)

urls = re.findall(r"https?://[^\"'\\\s]{0,300}?RF\.jsp[^\"'\\\s]{0,300}", html2, re.I)
print("RF.jsp urls in home:", len(urls), flush=True)
for u in urls[:5]:
    print("  ", u[:150], flush=True)
open(os.path.join(LOGS, "jnlp_home2_urls.txt"), "w", encoding="utf-8").write("\n".join(urls))
