#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_session - EBS 纯 HTTP 登录会话层（备用通道）

> ✅ 2026-11-04 最终结论：IE11 COM **完全可用**，是本技能登录主路径
> （见 erp_ie11.py）。本模块提供的是**纯 HTTP 备用通道** + 通道诊断。
> 之前「Win11 停用 IE11」是误判——根因是 360 的 `360chromeie.exe` 抢占了
> IE 内核 COM 注册，360 退出后 IE11 立即恢复。

## 通道现状（本机 2026-11-04 最终实测）

| 通道 | 结论 | 证据 |
|---|---|---|
| IE11 COM | ✅ 主路径 | `login-ie11 --no-fallback` 退出码 0，中文登录页填表 → 主页 |
| Edge 普通模式 / Playwright | 握手失败 | `ERR_SSL_VERSION_OR_CIPHER_MISMATCH` |
| Edge IE 模式 | 不适合自动化 | 无企业策略、无 COM DOM、不加载 Java 插件 |
| 360 浏览器 | 不用 | 运行时反而抢占 IE 内核 COM 注册，干扰 IE11 |
| 纯 HTTP | ✅ 备用 | 1.1s 登录，`prod` + `JSESSIONID`；但不承载 Forms |

## 本模块做什么

提供纯 HTTP 登录（复用 `erp_jws.login()`）+ 三通道诊断（`doctor`）。
不启动浏览器、不依赖 COM。**注意**：纯 HTTP 只解决登录，不承载 Forms
（Forms 需 IE11 的 Java 插件，走 `open-forms` / `erp_navigator`）。

用法：
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_session.py doctor
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_session.py login
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_session.py describe
"""
import html as htmlmod
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import erp_jws  # noqa: E402
from erp_common import ERP_USERNAME, safe_print  # noqa: E402

LINE = "=" * 62

#: 主页登录态判据（中文界面 / 英文界面）
_HOME_TITLE_MARKS = ("主页", "Home", "Oracle Applications")
_LOGIN_FORM_MARKS = ("usernameField", "passwordField")


# ── 通道诊断 ────────────────────────────────────────────────────────────
def probe_ie11_com(timeout=8.0):
    """探测 IE11 COM 是否还能创建。返回 dict(ok, detail)。

    只创建不可见实例并立刻 Quit，不导航、不打开可见窗口、不碰用户桌面。
    """
    res = {"ok": False, "detail": ""}
    ie = None
    try:
        import win32com.client
        ie = win32com.client.Dispatch("InternetExplorer.Application")
        try:
            ie.Visible = False
        except Exception:
            pass
        try:
            hwnd = int(ie.HWND)
            res["detail"] = f"COM 可创建，HWND={hwnd}"
            res["ok"] = hwnd > 0
        except Exception as e:
            res["detail"] = f"COM 可创建但拿不到 HWND（{type(e).__name__}: {str(e)[:80]}）"
    except Exception as e:
        code = ""
        try:
            code = f"0x{(e.args[0] & 0xFFFFFFFF):08X}"
        except Exception:
            pass
        res["detail"] = (f"{type(e).__name__} {code} {str(e)[:90]}".strip()
                         + "；若 360 浏览器（360se.exe / 360chromeie.exe）正在运行，"
                           "它会抢占 IE 内核 COM 注册导致此错——先让 360 退出再试。"
                           "IE11 本身可用（CLSID 注册完好，非 Win11 停用问题）")
    finally:
        if ie is not None:
            try:
                ie.Quit()
            except Exception:
                pass
    return res


def probe_edge_ie_mode():
    """检查 Edge IE 模式是否有企业站点列表策略。返回 dict(configured, detail)。

    注意：即使策略存在、IE 模式真的生效，它依然不提供 COM DOM、不加载 Java
    插件（见模块 docstring），所以本函数只用于解释现象，不作为选路依据。
    """
    res = {"configured": False, "detail": ""}
    found = []
    try:
        import winreg
        for hive, label in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"),
                            (winreg.HKEY_CURRENT_USER, "HKCU")):
            path = r"SOFTWARE\Policies\Microsoft\Edge"
            try:
                key = winreg.OpenKey(hive, path)
            except OSError:
                continue
            try:
                for name in ("InternetExplorerIntegrationLevel",
                             "InternetExplorerIntegrationSiteList"):
                    try:
                        val, _ = winreg.QueryValueEx(key, name)
                        found.append(f"{label}\\{name}={str(val)[:60]}")
                    except OSError:
                        pass
            finally:
                winreg.CloseKey(key)
    except Exception as e:
        res["detail"] = f"注册表读取异常：{e}"
        return res

    res["configured"] = bool(found)
    res["detail"] = ("; ".join(found) if found else
                     "HKLM/HKCU 的 Policies\\Microsoft\\Edge 均不存在，未配置企业站点列表")
    return res


def probe_http():
    """真连一次 ERP 做 HTTP 登录，返回 dict(ok, elapsed, home_url, detail)。"""
    res = {"ok": False, "elapsed": 0.0, "home_url": "", "detail": ""}
    t0 = time.time()
    try:
        op, jar, home_url = erp_jws.login()
        res["elapsed"] = round(time.time() - t0, 2)
        res["home_url"] = home_url
        res["ok"] = True
        names = [c.name for c in jar]
        res["detail"] = f"{res['elapsed']}s 登录成功，cookie={','.join(names[:6]) or '无'}"
        res["opener"] = op
        res["jar"] = jar
    except Exception as e:
        res["detail"] = f"{type(e).__name__}: {str(e)[:150]}"
    return res


# ── 登录 + 会话校验 ─────────────────────────────────────────────────────
def _parse_home(page):
    """从 EBS 主页 HTML 提取登录身份 / 标题（不做任何写操作）。"""
    out = {"title": "", "user": "", "logged_in": False}
    m = re.search(r"<title>(.*?)</title>", page, re.I | re.S)
    if m:
        out["title"] = htmlmod.unescape(m.group(1)).strip()
    m = re.search(r"登录身份\s*</span>\s*<span[^>]*>\s*([A-Za-z0-9_.-]+)\s*</span>",
                  page, re.I | re.S)
    if m:
        out["user"] = m.group(1).upper()
    elif re.search(r"Logged\s*In\s*As", page, re.I):
        m2 = re.search(r"Logged\s*In\s*As.{0,120}?([A-Z][A-Z0-9_.-]{2,})",
                       page, re.I | re.S)
        out["user"] = m2.group(1).upper() if m2 else ""
    has_title = any(k in out["title"] for k in _HOME_TITLE_MARKS)
    no_form = not any(k in page for k in _LOGIN_FORM_MARKS)
    out["logged_in"] = bool(has_title and no_form and out["user"])
    return out


def login(verify=True, verbose=True):
    """登录主入口。返回 dict；失败抛 RuntimeError。

    返回字段：opener / jar / home_url / elapsed / user / title / cookies。
    `opener` 可直接传给 `erp_jws.fetch_applet()`、`erp_jws.start()` 复用，
    避免重复登录。
    """
    t0 = time.time()
    op, jar, home_url = erp_jws.login()
    info = {"opener": op, "jar": jar, "home_url": home_url,
            "elapsed": round(time.time() - t0, 2),
            "cookies": [c.name for c in jar],
            "user": "", "title": "", "verified": False}

    if verify:
        page, final = erp_jws._get(op, home_url)
        home = _parse_home(page)
        info.update({"user": home["user"], "title": home["title"],
                     "verified": home["logged_in"], "final_url": final})
        if not home["logged_in"]:
            raise RuntimeError(
                f"登录态校验未通过：title={home['title']!r} user={home['user']!r} "
                f"url={final[:100]}")
    if verbose:
        safe_print(f"[OK] HTTP 登录成功（{info['elapsed']}s）")
        safe_print(f"     账号   : {info['user'] or ERP_USERNAME}")
        safe_print(f"     主页   : {info['title'] or '(未校验)'}")
        safe_print(f"     Cookie : {', '.join(info['cookies']) or '无'}")
        safe_print(f"     URL    : {home_url[:100]}")
    return info


def describe(verbose=True):
    """登录并实读主页信息，返回 login() 的结果 dict（含校验字段）。"""
    info = login(verify=True, verbose=False)
    if verbose:
        safe_print(LINE)
        safe_print(" EBS 登录会话（纯 HTTP 通道，无浏览器窗口）")
        safe_print(LINE)
        safe_print(f" 登录身份 : {info['user'] or ERP_USERNAME}")
        safe_print(f" 页面标题 : {info['title']}")
        safe_print(f" 主页 URL : {info['home_url'][:110]}")
        safe_print(f" 会话票据 : {', '.join(info['cookies']) or '无'}")
        safe_print(f" 校验结果 : {'通过' if info['verified'] else '未通过'}")
        safe_print(f" 耗时     : {info['elapsed']}s")
        safe_print(LINE)
    return info


def doctor():
    """一次性输出三条通道的可用性 + 选路结论。返回 0（主通道可用）/ 2（不可用）。"""
    safe_print(LINE)
    safe_print(" WHP-whirlpool-erp 登录通道诊断")
    safe_print(LINE)

    ie = probe_ie11_com()
    safe_print(f"[1] IE11 COM        {'可用' if ie['ok'] else '不可用'} - {ie['detail']}")

    edge = probe_edge_ie_mode()
    safe_print("[2] Edge IE 模式    不建议作为登录形式")
    safe_print(f"    企业策略 : {edge['detail']}")
    safe_print("    即使生效 : 不提供 COM DOM（OCR 定位不到用户名/口令输入框，"
               "logs/probe_edge3.log）")
    safe_print("               不加载 Java 插件（RF.jsp 等 180s 无 applet，"
               "logs/probe_edge3.log）")
    safe_print("    普通模式 : ERR_SSL_VERSION_OR_CIPHER_MISMATCH"
               "（logs/probe_edge4.log）")

    http = probe_http()
    safe_print(f"[3] 纯 HTTP        {'可用' if http['ok'] else '不可用'} - {http['detail']}")

    safe_print("-" * 62)
    if ie["ok"]:
        safe_print("结论：登录主路径 = IE11（erp_ops.py login-ie11）")
        safe_print("      IE11 COM 可用；纯 HTTP（login-http）作备用（不承载 Forms）。")
        safe_print("      若要拉 Forms：erp_ops.py open-forms <职责> <功能>（走 IE11）。")
        safe_print("      若 IE11 报 E_NOINTERFACE：先查 360 是否在跑（抢占 IE 内核 COM）。")
        return 0
    safe_print("结论：IE11 COM 当前不可用（常见原因：360 在跑，抢占 IE 内核 COM 注册）")
    if http["ok"]:
        safe_print("      纯 HTTP 可用，可临时 login-http，但它不承载 Forms；")
        safe_print("      建议退出 360 后重跑 doctor 复测 IE11。")
        return 0
    safe_print("结论：主通道与备用通道均不可用，请检查网络 / 密码（erp_ops.py check）")
    return 2


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "doctor"
    if cmd == "doctor":
        rc = doctor()
    elif cmd in ("login", "describe"):
        try:
            describe() if cmd == "describe" else login(verify=True)
            rc = 0
        except Exception as e:
            safe_print(f"[FAIL] 登录失败：{type(e).__name__}: {e}")
            rc = 2
    else:
        safe_print("用法: erp_session.py {doctor|login|describe}")
        rc = 1
    sys.exit(rc)


if __name__ == "__main__":
    main()
