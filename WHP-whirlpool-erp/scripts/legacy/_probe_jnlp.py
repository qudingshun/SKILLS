# -*- coding: utf-8 -*-
"""临时探针 6：纯 HTTP 登录 EBS，抓「更改组织」→ RF.jsp 的真实 HTML，找 JNLP 地址。

不启动任何浏览器。产物：
  logs/jnlp_login.html   登录页
  logs/jnlp_home.html    登录后首页
  logs/jnlp_rf.html      RF.jsp 返回体
（不要交付）
"""
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
LOGIN_URL = BASE + "/OA_HTML/AppsLogin?langCode=ZHS"
HOME_URL = (
    BASE + "/OA_HTML/OA.jsp?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
    "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y"
)

ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
ctx.minimum_version = ssl.TLSVersion.TLSv1
try:
    ctx.set_ciphers("DEFAULT@SECLEVEL=0")
except ssl.SSLError as e:
    print("set_ciphers:", e, flush=True)
# OP_LEGACY_SERVER_CONNECT：允许与老 OHS 做不安全的重协商
ctx.options |= 0x40000
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar),
    urllib.request.HTTPSHandler(context=ctx),
)
opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko")]


def get(url):
    with opener.open(url, timeout=60) as r:
        return r.read().decode("gbk", errors="replace"), r.geturl()


def post(url, data):
    body = urllib.parse.urlencode(data).encode("gbk")
    req = urllib.request.Request(url, data=body)
    with opener.open(req, timeout=60) as r:
        return r.read().decode("gbk", errors="replace"), r.geturl()


html, final = get(LOGIN_URL)
open(os.path.join(LOGS, "jnlp_login.html"), "w", encoding="utf-8").write(html)
print("login page:", final, len(html), flush=True)
for m in re.finditer(r"<(form|input|select)[^>]*>", html, re.I):
    tag = m.group(0)
    if "hidden" in tag.lower() or "form" in m.group(1).lower():
        print("  ", tag[:160], flush=True)

pwd = get_erp_password()
print("password loaded:", bool(pwd), flush=True)

data = {
    "usernameField": ERP_USERNAME,
    "passwordField": pwd,
    "SubmitButton": "登录",
    "langCode": "ZHS",
}
html2, final2 = post(LOGIN_URL, data)
open(os.path.join(LOGS, "jnlp_home.html"), "w", encoding="utf-8").write(html2)
print("after login:", final2, len(html2), flush=True)
print("has 职责:", "职责" in html2 or "责任" in html2, flush=True)

# 找 launchForm(...) 里跟「更改组织」相关的 URL
cands = re.findall(r"launchForm\([^)]*\)", html2)
print("launchForm count:", len(cands), flush=True)
for c in cands[:40]:
    if "更改组织" in c or "261" in c:
        print("LAUNCH:", c[:300], flush=True)
open(os.path.join(LOGS, "jnlp_launch.txt"), "w", encoding="utf-8").write(
    "\n".join(cands))
