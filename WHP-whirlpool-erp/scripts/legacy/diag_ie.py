#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""diag_ie - IE11 导航诊断（排查 RPC 服务器不可用）"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import win32com.client  # noqa: E402

URLS = [
    ("主页(带oas)", "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp"
                    "?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
                    "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y"
                    "&oapc=2&transactionid=1652645857&oas=BqTsZ_lSLwh9QeRE263_4g.."),
    ("登录页(中文)", "https://erp.whirlpool-china.com:4446/OA_HTML/AppsLogin?langCode=ZHS"),
    ("登录页(英文)", "https://erp.whirlpool-china.com:4446/OA_HTML/AppsLogin"),
]


def probe(ie, name, url):
    print(f"\n--- 导航: {name}\n    {url[:80]}")
    try:
        ie.Navigate(url)
    except Exception as e:
        print(f"    Navigate 异常: {e}")
        return False
    for i in range(20):
        time.sleep(1)
        try:
            t = ie.Document.title
            print(f"    [{i+1}s] title={t!r}")
            return True
        except Exception as e:
            print(f"    [{i+1}s] DOM 异常: {e}")
    return False


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    ie = win32com.client.Dispatch("InternetExplorer.Application")
    ie.Visible = True
    try:
        ie.Width = 1366
        ie.Height = 860
    except Exception:
        pass
    if mode == "single":
        for name, url in URLS:
            if not probe(ie, name, url):
                print(f"    -> {name} 失败")
                break
    elif mode == "zh-first":
        probe(ie, URLS[1][0], URLS[1][1])
    elif mode == "en":
        probe(ie, "登录页(英文)", URLS[2][1])
    elif mode == "zh-twice":
        probe(ie, URLS[1][0], URLS[1][1])
        probe(ie, URLS[1][0] + " (2nd)", URLS[1][1])
    else:
        probe(ie, URLS[0][0], URLS[0][1])
        probe(ie, URLS[1][0], URLS[1][1])
    try:
        ie.Quit()
    except Exception:
        pass


if __name__ == "__main__":
    main()
