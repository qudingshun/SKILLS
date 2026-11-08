#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_ie11 - 用 IE11（COM 自动化）登录惠而浦 EBS

背景：
  该 EBS 服务器（erp.whirlpool-china.com:4446）只支持过时的 TLS 版本/加密套件。
  Chromium 系浏览器（Edge 普通模式、Playwright 内核）已从代码中删除这些老套件，
  握手直接报 ERR_SSL_VERSION_OR_CIPHER_MISMATCH，加参数也无效。
  IE11 使用 Windows SCHANNEL/WinINET，本机 SecureProtocols=10912 已启用
  TLS 1.0/1.1/1.2/1.3，且 Oracle EBS 原生支持 IE11 —— 因此 IE11 可以完成
  TLS 握手并登录。这是经过实测验证的唯一 Chromium 之外的可行路径。

前置条件（本机已具备，首次运行若失败请检查）：
  1. WinINET 已启用老 TLS：
     注册表 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings
     的 SecureProtocols 含 TLS 1.0(0x80)/TLS 1.1(0x200)（本机为 10912，已含）。
  2. IE 保护模式已关闭（否则外部进程无法访问 DOM）：
     HKCU\\...\\Internet Settings\\Zones\\3 的 2500 = 3。
     （本技能运行时会自动检测并修复；恢复默认设 2500=0 即可）

  流程：
  启动 IE11 -> 打开 EBS -> 若在登录页则切换到简体中文登录页
  （AppsLogin?langCode=ZHS）-> 填账号密码 -> 提交 -> 等待主页 -> 截图

  ⚠️ 若 Dispatch 报 E_NOINTERFACE（"不支持此接口"），最常见原因是 360 浏览器
  （360se.exe / 360chromeie.exe）在运行、抢占了 IE 内核 COM 注册。
  退出 360 后 IE11 COM 立即恢复（2026-11-04 实测）。IE11 本身并未被 Win11 停用。

用法：
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ie11.py            # 有头，结束后自动关闭 IE
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ie11.py --keep     # 结束后保留 IE 窗口

IE 实例生命周期（重要约定）：
  脚本每次运行会开 IE 窗口。为免反复测试在桌面堆积实例，本模块用
  .cache/ie_instances.json 登记「本脚本开启的」IE 窗口 hwnd：
    启动前 -> 先关掉上一次遗留的实例（只关登记过的，绝不碰用户自己开的 IE）
    结束后 -> 默认自动关闭并清空登记（--keep 可保留）
"""
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import win32com.client  # noqa: E402

from erp_common import ERP_HOME_URL, ERP_USERNAME, safe_print, get_erp_password  # noqa: E402

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "erp.log")
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")
_INSTANCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", ".cache", "ie_instances.json")

# 简体中文登录页入口（实测 langCode=ZHS 直接返回中文登录页）
LOGIN_URL_ZH = "https://erp.whirlpool-china.com:4446/OA_HTML/AppsLogin?langCode=ZHS"
LOGOUT_URL = "https://erp.whirlpool-china.com:4446/OA_HTML/OALogout.jsp"

# 打开 EBS 的入口候选（按序尝试）。
# ERP_HOME_URL 里的 oas=... 是一次性会话 token，过期后服务端会拒绝导航
# （表现为 IE 停在 about:blank、title/body 皆空），故后面备了稳定入口兜底。
_OPEN_URLS = [
    ERP_HOME_URL,
    LOGIN_URL_ZH,
    "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp",
]

# 主页特征（中英双语，登录后按语言显示其一）
_HOME_MARKS = [
    "Logged In", "Main Menu", "Workflow", "Navigator", "Logout", "Preferences",
    "E-Business Suite", "主页", "职责", "欢迎", "注销", "首选项", "导航",
]
_LOGIN_MARKS = ["User Name", "用户名", "Password", "口令"]


def _log(msg):
    safe_print(msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# ── IE 实例生命周期管理（只关脚本自己开的窗口）────────────────────────
def _load_instances() -> list:
    """读取登记过的 IE 窗口 hwnd 列表"""
    try:
        if os.path.exists(_INSTANCE_FILE):
            with open(_INSTANCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [int(h) for h in data.get("hwnds", [])]
    except Exception:
        pass
    return []


def _save_instances(hwnds):
    try:
        os.makedirs(os.path.dirname(_INSTANCE_FILE), exist_ok=True)
        with open(_INSTANCE_FILE, "w", encoding="utf-8") as f:
            json.dump({"hwnds": sorted({int(h) for h in hwnds}),
                       "saved_at": datetime.datetime.now().isoformat()}, f)
    except Exception:
        pass


def _is_alive(hwnd) -> bool:
    try:
        import win32gui
        return bool(win32gui.IsWindow(int(hwnd)))
    except Exception:
        return False


def _wait_gone(hwnd, timeout: float = 3.0) -> bool:
    """等窗口真的消失；返回 True=已消失"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not _is_alive(hwnd):
            return True
        time.sleep(0.3)
    return not _is_alive(hwnd)


def _kill_window_process(hwnd) -> bool:
    """强制终止承载该窗口的进程（applet/插件常让 IE 拒绝温和关闭）"""
    try:
        import subprocess
        import win32process
        _tid, pid = win32process.GetWindowThreadProcessId(int(hwnd))
        if pid:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=15)
            return True
    except Exception:
        pass
    return False


def close_ie_hwnd(hwnd) -> bool:
    """
    关闭指定 hwnd 的 IE 窗口，逐级升级手段并**确认真的关掉**：
      COM Quit() -> WM_CLOSE -> 强制终止进程
    返回 True=窗口确已消失。
    """
    hwnd = int(hwnd)
    if not _is_alive(hwnd):
        return True

    # 1) 优雅关闭：COM Quit()
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        wins = shell.Windows()
        for i in range(wins.Count):
            try:
                w = wins.Item(i)
                if int(w.HWND) == hwnd:
                    w.Quit()
                    break
            except Exception:
                continue
    except Exception:
        pass
    if _wait_gone(hwnd, 3.0):
        return True

    # 2) 发 WM_CLOSE（IE 多标签或插件可能弹确认框）
    try:
        import win32con
        import win32gui
        if win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass
    if _wait_gone(hwnd, 2.5):
        return True

    # 3) 强制：终止承载进程（Java applet 会让 IE 拒绝前两种温和方式）
    _kill_window_process(hwnd)
    return _wait_gone(hwnd, 3.0)


def close_previous_instances(verbose: bool = True) -> int:
    """关闭上一次脚本运行遗留的 IE 实例（只关登记过的），并清空登记。"""
    hwnds = _load_instances()
    if not hwnds:
        return 0
    closed = 0
    for h in hwnds:
        if close_ie_hwnd(h):
            closed += 1
    _save_instances([])
    if verbose and closed:
        _log(f"[清理] 已关闭上次遗留的 {closed} 个 IE 实例")
    return closed


def register_instance(ie):
    """把本脚本刚创建的 IE 实例登记入册（供下次启动清理 / 本次结束关闭）"""
    try:
        hwnd = int(ie.HWND)
    except Exception:
        return None
    cur = _load_instances()
    if hwnd not in cur:
        cur.append(hwnd)
    _save_instances(cur)
    return hwnd


def register_hwnds(hwnds):
    """批量登记 hwnd（用于把 launchForm 衍生出的 applet 承载窗口也纳入管理）"""
    cur = _load_instances()
    for h in hwnds:
        try:
            ih = int(h)
        except Exception:
            continue
        if ih not in cur:
            cur.append(ih)
    _save_instances(cur)


def close_our_instances(verbose: bool = True) -> int:
    """关闭本脚本登记的全部 IE 实例并清空登记"""
    hwnds = _load_instances()
    closed = 0
    for h in hwnds:
        if close_ie_hwnd(h):
            closed += 1
    _save_instances([])
    if verbose and closed:
        _log(f"[清理] 已关闭本次开启的 {closed} 个 IE 实例")
    return closed


# ── IE 基础操作 ─────────────────────────────────────────────────────────
def enumerate_ie_windows():
    """
    枚举当前所有 IE 窗口（COM 对象级）。
    返回 [(ie_obj, hwnd, url, title)]，只含 erp 域名窗口。
    通过 Shell.Application 取 COM 对象（比按 hwnd 重新 Dispatch 稳）。
    """
    out = []
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        wins = shell.Windows()
        for i in range(wins.Count):
            try:
                w = wins.Item(i)
                if w is None:
                    continue
                url = (w.LocationURL or "")
                if not url:
                    continue
                # 只要我们自己用得上的 ERP 域
                if "erp.whirlpool-china.com" not in url:
                    continue
                hwnd = int(w.HWND)
                try:
                    title = w.Document.title or ""
                except Exception:
                    title = ""
                out.append((w, hwnd, url, title))
            except Exception:
                continue
    except Exception:
        pass
    return out


def find_logged_in_ie():
    """
    找一个已经登录 EBS 的 IE 窗口（供复用，**避免重复开浏览器**）。
    找到返回 (ie_obj, hwnd, url)；找不到返回 None。
    """
    try:
        for w, hwnd, url, title in enumerate_ie_windows():
            try:
                if is_logged_in(w):
                    return w, hwnd, url
            except Exception:
                continue
    except Exception:
        pass
    return None


def find_login_page_ie():
    """找一个停在 EBS 登录页的 IE 窗口（可直接填表登录，不开新窗口）"""
    try:
        for w, hwnd, url, title in enumerate_ie_windows():
            try:
                if is_login_page(w):
                    return w, hwnd, url
            except Exception:
                continue
    except Exception:
        pass
    return None


def logout_ebs(timeout: int = 40) -> bool:
    """
    注销 EBS 服务端会话。

    做法：新建一个**隐藏** IE 窗口访问 OALogout.jsp（与其它 IE 共享同一用户
    cookie 罐，注销全局生效）→ 等「已注销」迹象 → 关掉这个盖章用的窗口。
    主窗口不用再导航（同实例二次导航会崩 IE，见 SKILL.md 8.1）。

    返回 True=已触发注销（以页面出现登录迹象为准）。
    """
    for attempt in range(2):
        ie = None
        try:
            ie = win32com.client.Dispatch("InternetExplorer.Application")
            ie.Visible = False
            ie.Navigate(LOGOUT_URL)
        except Exception as e:
            _log(f"[注销] 打开注销页失败: {e}")
            if ie is not None:
                try:
                    close_ie_hwnd(int(ie.HWND))
                except Exception:
                    pass
            time.sleep(1)
            continue
        t0 = time.time()
        ok = False
        while time.time() - t0 < timeout:
            time.sleep(1)
            try:
                t = (ie.Document.title or "")
                txt = (ie.Document.body.innerText or "")[:300]
                # 注销成功的迹象：回到登录页 / 出现"注销"/登录表单
                if ("登录" in t) or ("usernameField" in _field_names(ie)) \
                        or ("User Name" in txt) or ("口令" in txt):
                    ok = True
                    break
                if not ie.Busy and t:
                    # 页面加载完了但没登录迹象 —— 再等几秒，等不到就放弃
                    if time.time() - t0 > timeout * 0.6:
                        break
            except Exception:
                continue
        try:
            close_ie_hwnd(int(ie.HWND))
        except Exception:
            pass
        if ok:
            _log("[注销] EBS 会话已注销（OALogout.jsp）")
            return True
        _log(f"[WARN] 注销迹象未确认（第 {attempt + 1} 次尝试）")
    return False


def cleanup_automation_leftovers(dry_run: bool = True) -> int:
    """
    发现（默认**不关闭**）本技能自动化可能遗留的窗口。

    ⚠️ 2026-11-04 事故修复：原实现把 `GetWindowRect` 坐标 < -20000 的
    `SunAwtFrame` 判为「屏幕外僵尸」并 WM_CLOSE + 强杀宿主进程。但
    **最小化的窗口坐标同样是 (-32000,-32000)**，结果把用户 13:20 正在使用的
    Forms 业务会话（`360chromeie.exe` → `jp2launcher.exe` 拉起）误杀。
    坐标无法区分「最小化」与「僵尸」，因此对 Forms 窗口一律**只报告、不关闭**。

    dry_run=True（默认）：只写日志、返回 0，不动任何窗口。
    dry_run=False：仅对「360 承接窗口」发 WM_CLOSE，且**不再强杀进程**；
                   由 `erp_ops.py cleanup --force` 显式触发。

    用户约定：不关闭用户自己开的浏览器 / Forms 窗口，不干预 360 的进程。
    """
    import win32con
    import win32gui
    targets = []
    forms = []

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
            l, t, r, b = win32gui.GetWindowRect(hwnd)
        except Exception:
            return
        if cls == "360se6_Frame" and title and (
                "erp.whirlpool-china.com" in title
                or "Oracle Applications" in title
                or "frmservlet" in title):
            targets.append((hwnd, cls, title, "360承接窗口"))
        elif cls == "SunAwtFrame" and (l < -20000 or t < -20000):
            # 只报告：最小化的业务窗口与僵尸窗口坐标无法区分，保护用户会话
            forms.append((hwnd, cls, title))

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass

    for hwnd, cls, title in forms:
        _log(f"[清理-保护] Forms 窗口 hwnd={hwnd} title={title[:60]!r}"
             " 疑似屏幕外/最小化，不自动关闭（避免误杀用户业务会话）")

    if dry_run:
        if targets:
            _log(f"[清理-预览] 发现 {len(targets)} 个 360 承接窗口，未自动关闭；"
                 "确需清理请跑 erp_ops.py cleanup --force")
        return 0

    closed = 0
    for hwnd, cls, title, why in targets:
        _log(f"[清理] {why}: hwnd={hwnd} class={cls} title={title[:60]!r}")
        try:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
        if _wait_gone(hwnd, 3.0):
            closed += 1
    if targets:
        _log(f"[清理] 共关闭 {closed}/{len(targets)} 个 360 承接窗口"
             "（未强杀任何进程）")
    return closed


def close_all(logout: bool = True) -> int:
    """
    统一收口：**可选先注销 EBS，再关闭本脚本登记的全部 IE 窗口**，最后
    清扫本技能的遗留垃圾窗口（360 承接页 / 屏幕外僵尸 Forms）。

    所有"程序要退出了"的场景一律走这里，保证：
      1) EBS 会话在服务端失效（不留孤儿登录态）；
      2) IE 窗口全部关闭（不堆积浏览器）；
      3) 360/僵尸窗口不留尾巴；
      4) 只关我们自己登记/开启的窗口，绝不碰用户自己开的浏览器。
    返回关闭的窗口数。
    """
    if logout:
        logout_ebs()
    closed = close_our_instances()
    try:
        closed += cleanup_automation_leftovers()
    except Exception:
        pass
    if logout:
        _log(f"[退出] EBS 已注销 + IE 已关闭 {closed} 个")
    else:
        _log(f"[退出] IE 已关闭 {closed} 个（未注销会话）")
    return closed


def wait_ready(ie, timeout=45):
    """等待 IE 导航/加载完成（ReadyState=4 且不 Busy）。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if not ie.Busy and ie.ReadyState >= 4:
                time.sleep(1.0)  # 等 OAF 前端脚本渲染
                try:
                    if not ie.Busy and ie.ReadyState >= 4:
                        return True
                except Exception:
                    return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def body_text(ie) -> str:
    try:
        return ie.Document.body.innerText or ""
    except Exception:
        return ""


def page_title(ie) -> str:
    try:
        return ie.Document.title or ""
    except Exception:
        return ""


def is_login_page(ie) -> bool:
    txt = body_text(ie) + page_title(ie)
    return ("usernameField" in _field_names(ie)) or any(m in txt for m in _LOGIN_MARKS)


def _field_names(ie) -> str:
    """返回页面所有 input 的 name 串（用于判断登录框是否存在）。"""
    try:
        doc = ie.Document
        names = []
        inputs = doc.getElementsByTagName("input")
        for i in range(60):
            try:
                el = inputs.item(i)
                if el is None:
                    break
                names.append(el.name or "")
            except Exception:
                break
        return " ".join(names)
    except Exception:
        return ""


def is_logged_in(ie) -> bool:
    txt = body_text(ie) + page_title(ie)
    if "usernameField" in _field_names(ie):
        return False
    return any(m in txt for m in _HOME_MARKS)


def find_logout_link(ie):
    """在主页找 Logout/注销 链接（用于清理会话后重新登录）。"""
    try:
        links = ie.Document.getElementsByTagName("a")
        for i in range(300):
            try:
                a = links.item(i)
                if a is None:
                    break
                t = (a.innerText or "").strip()
                if t in ("Logout", "注销"):
                    return a
            except Exception:
                break
    except Exception:
        pass
    return None


def fill_login_form(ie, password: str) -> bool:
    """填写经典 EBS 登录页（usernameField/passwordField/SubmitButton）。"""
    try:
        doc = ie.Document
        u = doc.getElementById("usernameField")
        p = doc.getElementById("passwordField")
        if u is None or p is None:
            _log("[IE11] [FAIL] 未找到登录表单字段")
            return False
        u.value = ERP_USERNAME
        p.value = password
        _log("[IE11] 已填写账号密码，点击登录...")
        btn = doc.getElementById("SubmitButton")
        if btn is not None:
            btn.click()
        else:
            # 兜底：找 Login 按钮
            btns = doc.getElementsByTagName("button")
            for i in range(20):
                try:
                    b = btns.item(i)
                    if b is None:
                        break
                    if (b.innerText or "").strip() in ("Login", "登录"):
                        b.click()
                        break
                except Exception:
                    break
        return True
    except Exception as e:
        _log(f"[IE11] 填表失败: {e}")
        # RPC 服务器不可用 = IE 实例已损坏，抛出去让上层重建实例
        if "RPC" in str(e):
            raise
        return False


def screenshot_ie(ie, path: str) -> bool:
    """
    截 IE 窗口图。

    首选 **PrintWindow**（窗口哪怕被其它窗口遮挡、不在前台，也能截到它
    自己的完整内容）。SetForegroundWindow 在 Windows 下经常被前台锁定
    拒绝，不可靠；ImageGrab 只在窗口真正到了最前面时才可靠，仅作兜底。
    """
    try:
        import win32gui
        hwnd = int(ie.HWND)

        # ① PrintWindow（PW_RENDERFULLCONTENT=2，Win8.1+ 用它截硬件加速窗口）
        try:
            import ctypes
            from PIL import Image
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            w, h = right - left, bottom - top
            if w > 0 and h > 0:
                user32 = ctypes.windll.user32
                gdi32 = ctypes.windll.gdi32
                wdc = user32.GetWindowDC(hwnd)
                mdc = gdi32.CreateCompatibleDC(wdc)
                bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
                gdi32.SelectObject(mdc, bmp)
                try:
                    if user32.PrintWindow(hwnd, mdc, 2):
                        class BMIH(ctypes.Structure):
                            _fields_ = [
                                ("biSize", ctypes.c_uint32),
                                ("biWidth", ctypes.c_long),
                                ("biHeight", ctypes.c_long),
                                ("biPlanes", ctypes.c_uint16),
                                ("biBitCount", ctypes.c_uint16),
                                ("biCompression", ctypes.c_uint32),
                                ("biSizeImage", ctypes.c_uint32),
                                ("biXPels", ctypes.c_long),
                                ("biYPels", ctypes.c_long),
                                ("biClrUsed", ctypes.c_uint32),
                                ("biClrImportant", ctypes.c_uint32),
                            ]
                        bi = BMIH()
                        bi.biSize = ctypes.sizeof(BMIH)      # 40
                        bi.biWidth = w
                        bi.biHeight = -h                     # top-down
                        bi.biPlanes = 1
                        bi.biBitCount = 32
                        buf = ctypes.create_string_buffer(w * h * 4)
                        gdi32.GetDIBits(mdc, bmp, 0, h, buf,
                                        ctypes.byref(bi), 0)
                        Image.frombuffer("RGB", (w, h), buf.raw, "raw",
                                         "BGRX", 0, 1).save(path)
                        return True
                finally:
                    gdi32.DeleteObject(bmp)
                    gdi32.DeleteDC(mdc)
                    user32.ReleaseDC(hwnd, wdc)
        except Exception as e:
            _log(f"[IE11] PrintWindow 截图失败，转 ImageGrab: {e}")

        # ② 兜底：置前 + 抓屏幕区域
        import ctypes
        from PIL import ImageGrab
        for _ in range(3):
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)   # ALT down
            try:
                win32gui.ShowWindow(hwnd, 9)                   # SW_RESTORE
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)   # ALT up
            time.sleep(0.5)
            try:
                if win32gui.GetForegroundWindow() == hwnd:
                    break
            except Exception:
                pass
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        ImageGrab.grab(bbox=(left, top, right, bottom)).save(path)
        return True
    except Exception as e:
        _log(f"[IE11] 截图失败: {e}")
        return False


# ── 主流程 ─────────────────────────────────────────────────────────────
def _dom_ok(ie, tries: int = 10, delay: float = 1.0) -> bool:
    """
    检查 IE 的 DOM 是否可访问（能取到 Document.title）。

    实测坑：导航后第一次访问 ie.Document 可能抛
    'RPC 服务器不可用'（IE 渲染进程刚重建 / 页面脚本崩溃）。
    这里做退避重试；若始终不可用，说明该 IE 实例已损坏，需要重建。
    """
    for i in range(tries):
        try:
            ie.Document.title
            return True
        except Exception as e:
            last = e
        time.sleep(delay)
    try:
        _log(f"[IE11] DOM 不可访问（{last}），该 IE 实例可能已损坏")
    except Exception:
        pass
    return False


def _is_chinese_login(ie) -> bool:
    """当前登录页是否是简体中文（'用户名'/'口令'）"""
    try:
        txt = body_text(ie)
    except Exception:
        return False
    return ("用户名" in txt) or ("口令" in txt) or (page_title(ie) == "登录")


def _new_ie(visible: bool = True):
    """新建（并登记）一个 IE 实例"""
    ie = win32com.client.Dispatch("InternetExplorer.Application")
    ie.Visible = visible
    try:
        ie.Width = 1366
        ie.Height = 860
    except Exception:
        pass
    register_instance(ie)
    return ie


def _open_entry(ie, password: str, lang: str, urls,
                navigate: bool = True) -> str:
    """
    用给定 IE 实例打开 EBS 并完成登录。

    ⚠️ 关键约束（2026-10-21 实测）：**同一个 IE 实例内做第二次 Navigate
    会让 IE 进程崩溃**（之后一律 'RPC 服务器不可用'）。因此：
      - 每个实例只做一次导航；
      - 需要换入口（尤其切中文登录页）时，**重建实例**再做；
      - 复用已有窗口时 navigate=False（页面已在当前窗口里，直接判态填写）。

    返回 'logged_in' / 'failed' / 'broken'（实例损坏）/ 'need_zh'（需换中文入口）。
    """
    if not navigate:
        urls = [None]              # 复用窗口：不再导航，直接检查当前页
    for url in urls:
        if url is not None:
            _log(f"[IE11] 打开 EBS: {url[:70]}...")
            try:
                ie.Navigate(url)
            except Exception as e:
                _log(f"[IE11] 导航异常: {e}")
                return "broken"
            wait_ready(ie, 40)
            if not _dom_ok(ie):
                return "broken"

        if is_logged_in(ie):
            _log("[IE11] [OK] 已处于登录态（IE 会话有效）")
            return "logged_in"

        if is_login_page(ie):
            _log(f"[IE11] 登录页 title={page_title(ie)!r}")
            if lang and not _is_chinese_login(ie):
                # 英文登录页：**不要在本网���再导航**（会崩），
                # 让外层重建实例、直接以中文入口重新打开。
                _log("[IE11] 当前是英文登录页，需换用中文登录入口（重建 IE 实例）")
                return "need_zh"
            try:
                filled = fill_login_form(ie, password)
            except Exception:
                return "broken"          # RPC 不可用 → 实例损坏
            if filled:
                t0 = time.time()
                while time.time() - t0 < 40:
                    time.sleep(1.5)
                    if is_logged_in(ie):
                        _log("[IE11] [OK] 登录成功，已进入 EBS 主页")
                        return "logged_in"
                    if (time.time() - t0 > 8 and is_login_page(ie)
                            and "Error" in body_text(ie)):
                        break
                _log("[IE11] [FAIL] 登录后未进入主页（账号密码错误或需额外验证）")
                return "failed"
            return "failed"

        # 既非登录页也非主页：换下一个候选入口（同实例再导航有风险，谨慎）
        txt = body_text(ie)
        _log(f"[IE11] 该入口未就绪（title={page_title(ie)!r}），"
             f"页面文本: {txt[:120]!r}")

    _log("[IE11] [FAIL] 所有入口都未就绪。"
         "若为 TLS 错误页：请确认注册表 SecureProtocols 已启用 TLS 1.0/1.1；"
         "若 DOM 不可访问：请确认 Zones\\3 的 2500=3（关闭保护模式）。")
    return "failed"


def open_and_login(visible: bool = True, lang: str = "ZHS", retries: int = 4):
    """
    打开 IE11 并登录 EBS，**返回 ie COM 对象**（供后续职责导航复用）。

    与 login_ie11 的区别：本函数不截图、不关闭 IE，把 ie 交还调用方，
    调用方拿到后可继续做「点职责 -> 进功能 -> 拉起 Forms」等操作。

    稳健性（2026-10-21 补）：
      - 强杀 IE 后的首屏空白 / 'RPC 服务器不可用' → 退避重试 + 重建实例；
      - 每个实例只导航一次；需要换入口就重建实例（否则 IE 会崩）。

    返回：ie 对象；密码缺失返回 None。是否登录成功请用 is_logged_in(ie) 判断。
    """
    password = get_erp_password()
    if not password:
        _log("[FAIL] 未找到 ERP 密码，请先运行 erp_secure_config.py 设置")
        return None

    # ⓪ 先清扫遗留垃圾（360 承接页 / 屏幕外僵尸 Forms），再谈复用
    try:
        cleanup_automation_leftovers()
    except Exception:
        pass

    # ① 先找现有 IE 窗口复用 —— **不重复开浏览器**（用户要求）
    #    - 已登录的窗口 → 直接复用去干活；
    #    - 停在登录页的窗口 → 在原窗口填表（不再导航，避免崩 IE）。
    try:
        hit = find_logged_in_ie()
        if hit:
            ie, hwnd, url = hit
            _log(f"[IE11] [OK] 复用已登录的 IE 窗口 hwnd={hwnd} "
                 f"url={url[:60]}（不开新窗口）")
            register_instance(ie)
            return ie
        hit = find_login_page_ie()
        if hit:
            ie, hwnd, url = hit
            _log(f"[IE11] 复用停在登录页的 IE 窗口 hwnd={hwnd}")
            register_instance(ie)
            state = _open_entry(ie, password, lang, [url], navigate=False)
            if state == "logged_in":
                return ie
            _log("[IE11] 复用窗口未能登录，改为新开窗口")
            # 只有登记过的窗口（我们自己开的）才关掉；用户手开的留给他自己处理
            if hwnd in _load_instances():
                try:
                    close_ie_hwnd(hwnd)
                except Exception:
                    pass
    except Exception:
        pass

    # ② 清掉上一次运行留下的 IE 实例，避免反复测试堆积窗口
    close_previous_instances()

    _log("[IE11] 启动 InternetExplorer.Application ...")
    ie = None
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        # 入口策略：第一次用"主页/稳定入口"（可复用已有会话）；
        # 之后一律用中文登录入口重建实例（避免同实例二次导航导致 IE 崩溃）。
        if attempt == 1:
            urls = [ERP_HOME_URL, LOGIN_URL_ZH]
        else:
            urls = [LOGIN_URL_ZH, ERP_HOME_URL]
        if ie is None:
            ie = _new_ie(visible)
        try:
            state = _open_entry(ie, password, lang, urls)
        except Exception as e:
            _log(f"[IE11] 打开过程异常（{e}），准备重建 IE 实例重试")
            state = "broken"
        if state == "logged_in":
            return ie
        if attempt < attempts:
            delay = 3 * attempt
            _log(f"[IE11] 第 {attempt} 次尝试未成功（{state}），"
                 f"{delay}s 后重建 IE 实例重试")
            try:
                close_ie_hwnd(int(ie.HWND))
            except Exception:
                pass
            # IE 关闭后 COM 对象可能仍残留，导致下一次 Dispatch 失败；
            # 强杀残留 iexplore 进程并多等片刻，再重建实例。
            try:
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "iexplore.exe"],
                               capture_output=True, timeout=15)
            except Exception:
                pass
            ie = None
            time.sleep(delay + 3)
    return ie


def login_ie11(visible: bool = True, close_after: bool = True,
               lang: str = "ZHS", logout: bool = True) -> int:
    """
    IE11 登录 EBS（一次性动作：登录 + 截图 + 结束后注销并关闭 IE）。
    返回 0=已登录/登录成功，2=失败，1=密码缺失。

    close_after: True（默认）= 脚本结束后注销 EBS 并关闭 IE；
                 False = 保留（调试时用 --keep）
    logout:      close_after=True 时是否先注销 EBS 会话（默认 True）
    lang:        登录页语言代码（ZHS=简体中文；空字符串=保持英文）
    """
    ie = open_and_login(visible=visible, lang=lang)
    if ie is None:
        return 1
    try:
        shot = os.path.join(SHOT_DIR, "ie11_login_success.png")
        shot_ok = screenshot_ie(ie, shot)
        _log(f"[IE11] 最终 title={page_title(ie)!r}")
        _log(f"[IE11] 页面文本片段: {body_text(ie)[:200]!r}")
        rc = 0 if is_logged_in(ie) else 2
        if shot_ok and os.path.exists(shot):
            _log(f"[IE11] 截图: {os.path.abspath(shot)}")
            _log(f"MEDIA:{os.path.abspath(shot)}")
        return rc
    finally:
        if close_after:
            # 注销 EBS 会话（服务端失效）+ 关闭全部登记的 IE 窗口
            close_all(logout=logout)
        else:
            _log("[IE11] 完成（IE 窗口按 --keep 保留；"
                 "退出时请跑 `erp_ops.py logout` 统一注销并关闭）")


def main():
    keep = "--keep" in sys.argv or "--keep-ie" in sys.argv
    lang = "" if ("--en" in sys.argv or "--lang=en" in sys.argv) else "ZHS"
    rc = login_ie11(visible=True, close_after=not keep, lang=lang,
                    logout=not keep)
    sys.exit(rc)


if __name__ == "__main__":
    main()
