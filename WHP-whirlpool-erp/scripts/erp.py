#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp - 惠而浦 ERP（Oracle EBS）单文件主入口
============================================

整合「打开 ERP（IE11 登录）+ 打开 Forms（职责导航 + launchForm 拉起）」的
完整核心链路到一个文件里，避免与测试/探测/旧代码混淆。

背景（2026-10 ~ 2026-11 实测定论）
----------------------------------
  * 服务器 erp.whirlpool-china.com:4446 只认老 TLS（TLS 1.0/1.1 + RSA 老套件）。
    Chromium 系（Edge / Playwright / 360 极速内核）握手必败
    （ERR_SSL_VERSION_OR_CIPHER_MISMATCH）。
  * IE11 走 Windows SCHANNEL/WinINET，能过老 TLS，是本技能**唯一可靠**的
    浏览器自动化路径。Oracle EBS 原生支持 IE11。
  * Forms 是 Java Applet（JInitiator 架构，非 JNLP）：由 IE11 + Java 8 插件
    （本机 jre1.8.0_191 32 位）运行 FormsLauncher applet，弹出独立 Java 窗口
    （class=SunAwtFrame，标题「Oracle Applications - 惠而浦（中国）ERP系统」）。

⚠️ 关键教训（务必记住）
  - 之前「Win11 停用 IE11 / IE11 已死」是**误判**。真正根因：360 浏览器的
    `360chromeie.exe`（兼容模式 IE 内核进程）在运行时抢占了 IE 内核的 COM 注册，
    导致 Dispatch("InternetExplorer.Application") 报 E_NOINTERFACE。
    **退出 360 后 IE11 立即恢复**（login --no-fallback 实测退出码 0）。
  - 因此：跑本脚本前必须先退出 360（360se.exe / 360chromeie.exe）。
  - 同一 IE 实例内第二次 Navigate 会让 IE 崩溃（RPC 服务器不可用），
    所以：每个实例只导航一次；需要切入口（如英文登录页→中文）时重建实例。

IE 实例生命周期（用户要求：对自己开启的网页负责）
  - 脚本只关**自己登记**的 IE 窗口（登记在 .cache/ie_instances.json），
    绝不碰用户自己开的浏览器 / Forms 窗口。
  - 每次运行前自动关闭上一次遗留的登记实例；运行结束默认注销 EBS + 关闭 IE。
  - 登录/测试失败需要重开登录页时，先关旧登录界面再重建（见 open_and_login）。

用法
----
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py login            # 登录（结束注销+关 IE）
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py login --keep     # 登录后保留窗口
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py open-forms "PO,SANYO合肥三洋物料计划员" "MRP计划员工作台"
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py list-funcs "PO,SANYO合肥三洋物料计划员"
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py logout           # 注销 EBS + 关登记的 IE
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp.py check            # 校验密码可解密

程序内复用（导入式）：
  import erp
  ie = erp.open_and_login()          # 登录，返回 IE COM 对象
  app = erp.open_function("职责名", "功能名")   # 登录+导航+拉 Forms，返回 FormsApp
  erp.close_all(logout=True)         # 收口：注销 + 关 IE
"""

import datetime
import getpass
import hashlib
import json
import os
import subprocess
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import win32com.client  # noqa: E402
import win32gui  # noqa: E402
import pythoncom  # noqa: E402

# InternetExplorer.Application 的 CLSID 与 IID（用于绕开 ProgID 被 360 劫持的情况）
_IE_CLSID = "{0002DF01-0000-0000-C000-000000000046}"
_IE_IID_IDISPATCH = "{00020400-0000-0000-C000-000000000046}"

# Forms 是 32 位 Java 应用，pywinauto 的位数提示噪音较大，静音（功能不受影响）
warnings.filterwarnings("ignore", message="32-bit application should be automated*")


# ══════════════════════════════════════════════════════════════════════
# 一、常量 / 路径 / 账号
# ══════════════════════════════════════════════════════════════════════
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(_BASE_DIR)

ERP_HOME_URL = (
    "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp"
    "?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
    "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y"
    "&oapc=2&transactionid=1652645857&oas=BqTsZ_lSLwh9QeRE263_4g.."
)
# 稳定主页入口（不带一次性 oas token，不会因 token 过期落到 Error Page）
ERP_HOME_URL_STABLE = (
    "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp"
    "?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
    "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y&oapc=2"
)
ERP_USERNAME = "hsa697"

LOGIN_URL_ZH = "https://erp.whirlpool-china.com:4446/OA_HTML/AppsLogin?langCode=ZHS"
LOGOUT_URL = "https://erp.whirlpool-china.com:4446/OA_HTML/OALogout.jsp"

LOG_FILE = os.path.join(PROJECT_DIR, "logs", "erp.log")
SHOT_DIR = os.path.join(PROJECT_DIR, "logs")
_INSTANCE_FILE = os.path.join(PROJECT_DIR, ".cache", "ie_instances.json")

# 打开 EBS 的入口候选（首选稳定入口，避免过期 oas token 落到 Error Page）
_OPEN_URLS = [
    ERP_HOME_URL_STABLE,
    "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp",
    LOGIN_URL_ZH,
    ERP_HOME_URL,
]

# 主页 / 登录页特征（中英双语）。
# 注意：不要用 "Logout"/"Preferences" 这类宽泛词（Error Page 也有），
# 主页判据用「登录身份」「主菜单」等主页特有文本。
_HOME_MARKS = [
    "Logged In As", "登录身份", "主菜单", "Main Menu", "职责", "欢迎",
    "E-Business Suite", "Workflow", "Navigator", "导航", "首选项",
]
_LOGIN_MARKS = ["User Name", "用户名", "Password", "口令"]

# Forms 窗口特征
FORMS_WINDOW_CLASS = "SunAwtFrame"
FORMS_WINDOW_TITLE_MARK = "Oracle Applications"
LAUNCH_PREFIX = "javascript:launchForm("

# 主页（职责列表页）备用入口（不带一次性 oas token）
HOME_URL_PLAIN = (
    "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp"
    "?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
    "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y&oapc=2"
)


# ══════════════════════════════════════════════════════════════════════
# 二、公共工具
# ══════════════════════════════════════════════════════════════════════
_UNICODE_SAFE_MAP = {
    "\u2713": "[OK]", "\u2714": "[OK]", "\u2716": "[X]", "\u2705": "[OK]",
    "\u274c": "[X]", "\u23f3": "[WAIT]", "\u26a0": "[WARN]", "\ufe0f": "",
    "\u279c": "->",
}


def safe_print(*args, sep=" ", **kwargs):
    cleaned = []
    encoding = sys.stdout.encoding or "utf-8"
    for a in args:
        s = str(a)
        try:
            s.encode(encoding)
            cleaned.append(s)
        except (UnicodeEncodeError, UnicodeDecodeError):
            for char, repl in _UNICODE_SAFE_MAP.items():
                s = s.replace(char, repl)
            s = s.encode(encoding, errors="replace").decode(encoding, errors="replace")
            cleaned.append(s)
    print(*cleaned, sep=sep, **kwargs)


def _log(msg):
    safe_print(msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════
# 三、密码加密读取（AES-256，明文绝不落盘）
# ══════════════════════════════════════════════════════════════════════
_PASSWORD_DIR = os.path.join(PROJECT_DIR, "erp_runtime_config", "passwords")
_PASSWORD_SALT = "WPOOL_ERP_V1"


def _master_key() -> bytes:
    seed = f"{os.getenv('USERNAME')}|{os.getenv('COMPUTERNAME')}|{_PASSWORD_SALT}"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def _aes_decrypt(ciphertext: bytes) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    iv = ciphertext[:16]
    data = ciphertext[16:]
    cipher = Cipher(algorithms.AES(_master_key()), modes.CBC(iv))
    dec = cipher.decryptor()
    padded = dec.update(data) + dec.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")


def get_erp_password():
    """从加密存储读取 ERP 密码；未设置返回 None。"""
    filepath = os.path.join(_PASSWORD_DIR, "erp_password.dat")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "rb") as f:
            enc = f.read()
        return _aes_decrypt(enc)
    except Exception as e:
        safe_print(f"[安全] 密码加载失败: {e}")
        return None


def _aes_encrypt(plaintext: str) -> bytes:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    cipher = Cipher(algorithms.AES(_master_key()), modes.CBC(iv))
    enc = cipher.encryptor()
    return iv + enc.update(padded) + enc.finalize()


def set_erp_password(password: str) -> bool:
    """加密保存 ERP 密码（仅密文落盘）。"""
    try:
        os.makedirs(_PASSWORD_DIR, exist_ok=True)
        filepath = os.path.join(_PASSWORD_DIR, "erp_password.dat")
        with open(filepath, "wb") as f:
            f.write(_aes_encrypt(password))
        safe_print(f"[安全] ERP 密码已加密保存 -> {filepath}")
        return True
    except Exception as e:
        safe_print(f"[安全] 保存失败: {e}")
        return False


def interactive_setup():
    """交互式设置 ERP 密码（明文仅经 stdin/内存，绝不落盘）。"""
    safe_print("\n" + "=" * 56)
    safe_print("  WHP ERP 安全密码设置（明文仅经 stdin/内存，绝不落盘）")
    safe_print("=" * 56)
    try:
        if sys.stdin and sys.stdin.isatty():
            pw = getpass.getpass("\n请输入 ERP 密码（输入不可见，留空跳过）：")
        else:
            pw = input("\n请输入 ERP 密码（留空跳过）：").strip()
    except Exception:
        pw = input("\n请输入 ERP 密码（留空跳过）：").strip()
    if pw:
        set_erp_password(pw)
    else:
        safe_print("[跳过] 未输入密码")
    safe_print("\n设置完成。")


# ══════════════════════════════════════════════════════════════════════
# 四、IE 实例生命周期管理（只关脚本自己开的窗口）
# ══════════════════════════════════════════════════════════════════════
def _load_instances() -> list:
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
        return bool(win32gui.IsWindow(int(hwnd)))
    except Exception:
        return False


def _wait_gone(hwnd, timeout: float = 3.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not _is_alive(hwnd):
            return True
        time.sleep(0.3)
    return not _is_alive(hwnd)


def _kill_window_process(hwnd) -> bool:
    try:
        import win32process
        _tid, pid = win32process.GetWindowThreadProcessId(int(hwnd))
        if pid:
            subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=15)
            return True
    except Exception:
        pass
    return False


def close_ie_hwnd(hwnd) -> bool:
    """关闭指定 hwnd 的 IE 窗口：COM Quit -> WM_CLOSE -> 强杀进程。"""
    hwnd = int(hwnd)
    if not _is_alive(hwnd):
        return True
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
    try:
        import win32con
        if win32gui.IsWindow(hwnd):
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    except Exception:
        pass
    if _wait_gone(hwnd, 2.5):
        return True
    _kill_window_process(hwnd)
    return _wait_gone(hwnd, 3.0)


def close_previous_instances(verbose: bool = True) -> int:
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
    hwnds = _load_instances()
    closed = 0
    for h in hwnds:
        if close_ie_hwnd(h):
            closed += 1
    _save_instances([])
    if verbose and closed:
        _log(f"[清理] 已关闭本次开启的 {closed} 个 IE 实例")
    return closed


def _is_360_running() -> bool:
    """检测 360 浏览器（360se.exe / 360chromeie.exe）是否在运行。"""
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            try:
                name = (p.info["name"] or "").lower()
            except Exception:
                continue
            if name in ("360se.exe", "360chromeie.exe"):
                return True
    except Exception:
        pass
    # psutil 不可用时的兜底：用 tasklist
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq 360se.exe"],
                             capture_output=True, text=True, errors="replace",
                             timeout=10)
        return "360se.exe" in (out.stdout or "")
    except Exception:
        pass
    return False


# ══════════════════════════════════════════════════════════════════════
# 五、IE 基础操作（枚举 / 登录态判断 / 填表 / 截图 / 注销）
# ══════════════════════════════════════════════════════════════════════
def enumerate_ie_windows():
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
                if not url or "erp.whirlpool-china.com" not in url:
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
    """用隐藏 IE 窗口访问 OALogout.jsp 注销 EBS 服务端会话。"""
    for attempt in range(2):
        ie = None
        try:
            ie = _new_ie(visible=False)
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
                if ("登录" in t) or ("usernameField" in _field_names(ie)) \
                        or ("User Name" in txt) or ("口令" in txt):
                    ok = True
                    break
                if not ie.Busy and t and time.time() - t0 > timeout * 0.6:
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


def close_all(logout: bool = True) -> int:
    """统一收口：可选先注销 EBS，再关闭本脚本登记的全部 IE 窗口。"""
    if logout:
        logout_ebs()
    closed = close_our_instances()
    if logout:
        _log(f"[退出] EBS 已注销 + IE 已关闭 {closed} 个")
    else:
        _log(f"[退出] IE 已关闭 {closed} 个（未注销会话）")
    return closed


def wait_ready(ie, timeout=45):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if not ie.Busy and ie.ReadyState >= 4:
                time.sleep(1.0)
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


def _field_names(ie) -> str:
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


def is_login_page(ie) -> bool:
    txt = body_text(ie) + page_title(ie)
    return ("usernameField" in _field_names(ie)) or any(m in txt for m in _LOGIN_MARKS)


def is_logged_in(ie) -> bool:
    txt = body_text(ie) + page_title(ie)
    if "usernameField" in _field_names(ie):
        return False
    return any(m in txt for m in _HOME_MARKS)


def fill_login_form(ie, password: str) -> bool:
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
        if "RPC" in str(e):
            raise
        return False


def screenshot_ie(ie, path: str) -> bool:
    """截 IE 窗口图（PrintWindow 优先，ImageGrab 兜底）。"""
    try:
        hwnd = int(ie.HWND)
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
                        bi.biSize = ctypes.sizeof(BMIH)
                        bi.biWidth = w
                        bi.biHeight = -h
                        bi.biPlanes = 1
                        bi.biBitCount = 32
                        buf = ctypes.create_string_buffer(w * h * 4)
                        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
                        Image.frombuffer("RGB", (w, h), buf.raw, "raw",
                                         "BGRX", 0, 1).save(path)
                        return True
                finally:
                    gdi32.DeleteObject(bmp)
                    gdi32.DeleteDC(mdc)
                    user32.ReleaseDC(hwnd, wdc)
        except Exception as e:
            _log(f"[IE11] PrintWindow 截图失败，转 ImageGrab: {e}")
        import ctypes
        from PIL import ImageGrab
        for _ in range(3):
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)
            try:
                win32gui.ShowWindow(hwnd, 9)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)
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


# ══════════════════════════════════════════════════════════════════════
# 六、登录主流程
# ══════════════════════════════════════════════════════════════════════
def _dom_ok(ie, tries: int = 10, delay: float = 1.0) -> bool:
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
    try:
        txt = body_text(ie)
    except Exception:
        return False
    return ("用户名" in txt) or ("口令" in txt) or (page_title(ie) == "登录")


def _new_ie(visible: bool = True):
    """
    创建 IE 实例，按优先级依次尝试多种方式，任一成功即返回：
      1. Dispatch(ProgID) —— 常规路径
      2. DispatchEx(ProgID) —— 强制新实例（绕过 360 可能的进程内对象复用）
      3. CoCreateInstance(CLSID, LOCAL_SERVER) —— 直接按 CLSID 实例化真 IE，
         绕开 ProgID 解析（360 的 360chromeie.exe 可能在运行时劫持 ProgID 解析）
      4. 直接启动 iexplore.exe 独立进程，再经 Shell.Windows 按 hwnd 找回 COM 对象
    这样即使 360 在运行、劫持了某条路径，其余路径仍可能拿到真正的 IE11。
    """
    # 方式 1：ProgID Dispatch
    try:
        ie = win32com.client.Dispatch("InternetExplorer.Application")
        if _ie_is_usable(ie):
            return _finalize_ie(ie, visible)
    except Exception:
        pass

    # 方式 2：DispatchEx
    try:
        ie = win32com.client.DispatchEx("InternetExplorer.Application")
        if _ie_is_usable(ie):
            return _finalize_ie(ie, visible)
    except Exception:
        pass

    # 方式 3：按 CLSID 直接 CoCreateInstance（LOCAL_SERVER）
    try:
        obj = pythoncom.CoCreateInstance(
            pythoncom.MakeIID(_IE_CLSID), None,
            pythoncom.CLSCTX_LOCAL_SERVER, pythoncom.MakeIID(_IE_IID_IDISPATCH))
        ie = win32com.client.Dispatch(obj)
        if _ie_is_usable(ie):
            return _finalize_ie(ie, visible)
    except Exception:
        pass

    # 方式 4：直接启动 iexplore.exe，再经 Shell.Windows 找回
    try:
        return _new_ie_via_process(visible)
    except Exception:
        pass

    # 全部失败：抛最后一条异常信息，让上层走诊断
    raise RuntimeError(
        "无法创建 IE 实例（所有路径均失败）。若 360 浏览器正在运行，"
        "它可能劫持了 IE 内核 COM；请退出 360 后重试。")


def _ie_is_usable(ie) -> bool:
    """判断拿到的 COM 对象是否是真正可用的 IE（能取到 HWND）。"""
    try:
        int(ie.HWND)
        return True
    except Exception:
        return False


def _finalize_ie(ie, visible: bool = True):
    ie.Visible = visible
    try:
        ie.Width = 1366
        ie.Height = 860
    except Exception:
        pass
    register_instance(ie)
    return ie


def _new_ie_via_process(visible: bool = True):
    """兜底：直接启动 iexplore.exe，再经 Shell.Windows 找回其 COM 对象。"""
    exe = r"C:\Program Files\Internet Explorer\iexplore.exe"
    subprocess.Popen([exe, "about:blank"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            shell = win32com.client.Dispatch("Shell.Application")
            wins = shell.Windows()
            for i in range(wins.Count):
                try:
                    w = wins.Item(i)
                    if not w:
                        continue
                    name = (w.FullName or "").lower()
                    if "iexplore" in name and _ie_is_usable(w):
                        return _finalize_ie(w, visible)
                except Exception:
                    continue
        except Exception:
            pass
    raise RuntimeError("直接启动 iexplore.exe 后未能找回其 COM 对象")


def _open_entry(ie, password: str, lang: str, urls, navigate: bool = True) -> str:
    """用给定 IE 实例打开 EBS 并登录。返回 logged_in/failed/broken/need_zh。"""
    if not navigate:
        urls = [None]
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
                _log("[IE11] 当前是英文登录页，需换用中文登录入口（重建 IE 实例）")
                return "need_zh"
            try:
                filled = fill_login_form(ie, password)
            except Exception:
                return "broken"
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
        txt = body_text(ie)
        _log(f"[IE11] 该入口未就绪（title={page_title(ie)!r}），"
             f"页面文本: {txt[:120]!r}")
    _log("[IE11] [FAIL] 所有入口都未就绪。"
         "若为 TLS 错误页：请确认注册表 SecureProtocols 已启用 TLS 1.0/1.1；"
         "若 DOM 不可访问：请确认 Zones\\3 的 2500=3（关闭保护模式）。")
    return "failed"


def open_and_login(visible: bool = True, lang: str = "ZHS", retries: int = 4):
    """打开 IE11 并登录 EBS，返回 ie COM 对象（供后续职责导航复用）。"""
    password = get_erp_password()
    if not password:
        _log("[FAIL] 未找到 ERP 密码，请先运行 erp.py setup 设置")
        return None

    # 360 运行时可能劫持 IE 内核 COM，导致 Dispatch 报 E_NOINTERFACE。
    # 不在这里硬拦截——`_new_ie` 已做多路径兜底（Dispatch → DispatchEx →
    # CLSID 直建 → 独立启动 iexplore.exe），任一路径拿到真 IE 即继续。
    # 仅当 360 在跑时给一句软提示，真正失败时才在上层报错并提示退出 360。
    if _is_360_running():
        _log("[提示] 检测到 360 浏览器正在运行，将尝试多路径创建 IE（可能仍能成功）。")

    # 复用已有 IE 窗口（不重复开浏览器）
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
            if hwnd in _load_instances():
                try:
                    close_ie_hwnd(hwnd)
                except Exception:
                    pass
    except Exception:
        pass

    # 清掉上一次运行留下的 IE 实例，避免堆积
    close_previous_instances()

    _log("[IE11] 启动 InternetExplorer.Application ...")
    ie = None
    attempts = max(1, retries)
    for attempt in range(1, attempts + 1):
        # 入口策略：首选稳定主页入口（不含过期 oas token）；之后一律用
        # 中文登录入口重建实例（避免同实例二次导航导致 IE 崩溃）。
        if attempt == 1:
            urls = [ERP_HOME_URL_STABLE, LOGIN_URL_ZH]
        else:
            urls = [LOGIN_URL_ZH, ERP_HOME_URL_STABLE]
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
            try:
                subprocess.run(["taskkill", "/F", "/IM", "iexplore.exe"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=15)
            except Exception:
                pass
            ie = None
            time.sleep(delay + 3)
    return ie


# ══════════════════════════════════════════════════════════════════════
# 七、职责导航 + 拉起 Forms
# ══════════════════════════════════════════════════════════════════════
class IeBroken(RuntimeError):
    """IE 实例已损坏（二次导航崩溃 / RPC 不可用）——需重建并重新登录"""


def _iter_links(doc):
    links = doc.getElementsByTagName("a")
    for i in range(links.length):
        try:
            el = links.item(i)
            if el is None:
                break
            t = (el.innerText or "").strip().replace("\r\n", " ")
            try:
                h = el.href or ""
            except Exception:
                h = ""
            yield i, el, t, h
        except Exception:
            continue


def _has_resp_links(ie) -> bool:
    doc = ie.Document
    try:
        links = doc.getElementsByTagName("a")
        for i in range(links.length):
            try:
                el = links.item(i)
                if el is None:
                    break
                h = el.href or ""
                t = (el.innerText or "").strip()
            except Exception:
                continue
            if h.endswith("#") and t:
                return True
    except Exception:
        pass
    return False


def _wait_home(ie, timeout: int = 20) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if _has_resp_links(ie):
                return True
        except Exception:
            pass
        try:
            txt = body_text(ie)
        except Exception:
            txt = ""
        if any(m in txt for m in ("主菜单", "Oracle Applications 主页",
                                  "Main Menu", "Logged In")):
            if _has_resp_links(ie):
                return True
        time.sleep(1)
    try:
        txt = body_text(ie)
        return any(m in txt for m in ("主菜单", "Oracle Applications 主页",
                                      "Main Menu", "Logged In"))
    except Exception:
        return False


def ensure_homepage(ie, timeout: int = 30) -> bool:
    if _has_resp_links(ie):
        return True
    for url in (ERP_HOME_URL, HOME_URL_PLAIN):
        _log(f"[导航] 当前不在主页，返回主页: {url[:70]}...")
        try:
            ie.Navigate(url)
        except Exception as e:
            _log(f"[导航] 导航异常: {e}")
            raise IeBroken(f"导航主页失败: {e}")
        wait_ready(ie, timeout)
        if not _dom_ok(ie, tries=3, delay=1.0):
            raise IeBroken("返回主页后 IE DOM 不可访问，实例已损坏")
        if _wait_home(ie, timeout=20):
            _log("[导航] 已回到主页")
            return True
    return False


def find_resp_node(ie, resp_name: str):
    try:
        lis = ie.Document.getElementsByTagName("li")
    except Exception:
        return None
    for i in range(lis.length):
        try:
            li = lis.item(i)
            if li is None:
                break
            if resp_name in (li.innerText or ""):
                return li
        except Exception:
            continue
    return None


def resp_function_links(ie, li) -> list:
    out = []
    if li is None:
        return out
    try:
        links = li.getElementsByTagName("a")
    except Exception:
        return out
    for i in range(links.length):
        try:
            el = links.item(i)
            if el is None:
                break
            h = el.href or ""
            if not h.startswith(LAUNCH_PREFIX):
                continue
            t = (el.innerText or "").strip().replace("\r\n", " ")
            url = h[len(LAUNCH_PREFIX):].rstrip(")").strip().strip("'")
            out.append({"name": t, "url": url, "el": el})
        except Exception:
            continue
    return out


def expand_responsibility(ie, resp_name: str, timeout: int = 25,
                          allow_click: bool = True) -> bool:
    t0 = time.time()
    li = None
    while time.time() - t0 < timeout:
        li = find_resp_node(ie, resp_name)
        if li is not None:
            break
        time.sleep(1)
    if li is None:
        _log(f"[导航] 当前页未见职责「{resp_name}」，先回主页再重试")
        if ensure_homepage(ie):
            t0 = time.time()
            while time.time() - t0 < 15:
                li = find_resp_node(ie, resp_name)
                if li is not None:
                    break
                time.sleep(1)
        if li is None:
            avail = list_responsibilities(ie)
            _log(f"[FAIL] 主页未找到职责链接: {resp_name}")
            if avail:
                _log(f"[提示] 主页当前可见职责: {avail}")
            return False

    funcs = resp_function_links(ie, li)
    if funcs:
        _log(f"[导航] 职责「{resp_name}」已展开，直接读取到 {len(funcs)} 个功能"
             f"（无需点击，避免点崩 IE）")
        return True

    if not allow_click:
        _log(f"[FAIL] 职责「{resp_name}」未展开且未允许点击展开")
        return False

    _log(f"[导航] 职责「{resp_name}」未展开，尝试点击展开 ...")
    try:
        target = None
        imgs = li.getElementsByTagName("img")
        for i in range(imgs.length):
            try:
                im = imgs.item(i)
                if im is not None and (im.alt or "").lower() == "expand":
                    target = im
                    break
            except Exception:
                continue
        if target is None:
            anchors = li.getElementsByTagName("a")
            target = anchors.item(0) if anchors.length else None
        if target is None:
            _log("[FAIL] 职责节点里找不到可点击的展开元素")
            return False
        n_before = len(resp_function_links(ie, li))
        target.click()
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(1)
            if not _dom_ok(ie, tries=1, delay=0.2):
                raise IeBroken("点击职责展开后 IE 崩溃")
            n_now = len(resp_function_links(ie, li))
            if n_now > n_before:
                _log(f"[导航] 职责已展开（功能链接 {n_before} -> {n_now}）")
                return True
    except IeBroken:
        raise
    except Exception as e:
        _log(f"[WARN] 点击展开失败: {e}")
        return False
    _log("[WARN] 点击职责后功能链接未增加（可能本已展开，继续尝试找功能）")
    return True


def list_responsibilities(ie) -> list:
    out = []
    try:
        for _, _, t, h in _iter_links(ie.Document):
            if h.endswith("#") and t and t not in out:
                out.append(t)
    except Exception:
        pass
    return out


def read_function_url(ie, func_name: str, resp_name: str = ""):
    cand = []
    if resp_name:
        li = find_resp_node(ie, resp_name)
        cand = resp_function_links(ie, li)
    else:
        for _, el, t, h in _iter_links(ie.Document):
            if h.startswith(LAUNCH_PREFIX):
                cand.append({"name": t,
                             "url": h[len(LAUNCH_PREFIX):].rstrip(")").strip().strip("'")})
    first_hit = None
    for f in cand:
        if f["name"] == func_name:
            return f["url"]
        if first_hit is None and func_name in f["name"]:
            first_hit = f
    return first_hit["url"] if first_hit else None


def open_forms_window(url: str, visible: bool = True, width: int = 1366,
                      height: int = 900):
    try:
        ie2 = _new_ie(visible=visible)
        try:
            ie2.Width = width
            ie2.Height = height
        except Exception:
            pass
        _log(f"[导航] 新开 IE 窗口加载 Forms: {url[:140]}")
        ie2.Navigate(url)
        return ie2
    except Exception as e:
        _log(f"[FAIL] 新开 IE 窗口失败: {e}")
        return None


def list_functions(ie, func_filter: str = "", resp_name: str = "") -> list:
    out = []
    if resp_name:
        li = find_resp_node(ie, resp_name)
        for f in resp_function_links(ie, li):
            if func_filter and func_filter not in f["name"]:
                continue
            out.append({"name": f["name"], "url": f["url"]})
        return out
    for _, _, t, h in _iter_links(ie.Document):
        if h.startswith(LAUNCH_PREFIX):
            if func_filter and func_filter not in t:
                continue
            url = h[len(LAUNCH_PREFIX):].rstrip(")").strip().strip("'").strip()
            out.append({"name": t, "url": url})
    return out


def snapshot_forms_windows() -> dict:
    out = {}

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            return
        if cls == FORMS_WINDOW_CLASS and FORMS_WINDOW_TITLE_MARK in title:
            out[hwnd] = title

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return out


def wait_new_forms_window(before: dict, timeout: int = 150):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(3)
        now = snapshot_forms_windows()
        for hwnd, title in now.items():
            if hwnd not in before:
                return hwnd, title
    return None


def snapshot_ie_windows() -> dict:
    out = {}

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            return
        if cls == "IEFrame":
            try:
                out[hwnd] = win32gui.GetWindowText(hwnd)
            except Exception:
                out[hwnd] = ""

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return out


# ══════════════════════════════════════════════════════════════════════
# 八、FormsApp 驱动类（pywinauto）
# ══════════════════════════════════════════════════════════════════════
class FormsApp:
    """
    Oracle Forms Java 窗口的 pywinauto 封装。
    Java AWT(SunAwtFrame) 对 UIA 只暴露 TitleBar，驱动靠 win32 backend
    （set_focus / type_keys / 菜单 / 截图 / 坐标点击）。
    """

    def __init__(self, backend: str = "uia"):
        from pywinauto import Application
        self.Application = Application
        self.app = None
        self.window = None
        self.backend = backend

    def connect(self, title=None, title_re=None, timeout: int = 60):
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            try:
                self.app = self.Application(backend=self.backend).connect(
                    title=title, title_re=title_re, timeout=3)
                wins = self.app.windows()
                if wins:
                    self.window = wins[0]
                    safe_print(f"[Forms] 已连接窗口: {self.window.window_text()}")
                    return True
            except Exception as e:
                last_err = e
                time.sleep(2)
        safe_print(f"[FAIL] 未能连接到 Forms 窗口: {last_err}")
        return False

    def connect_by_hwnd(self, hwnd: int, timeout: int = 30) -> bool:
        deadline = time.time() + timeout
        last_err = None
        while time.time() < deadline:
            try:
                self.app = self.Application(backend="win32").connect(
                    handle=hwnd, timeout=3)
                self.window = self.app.window(handle=hwnd)
                safe_print(f"[Forms] 已连接窗口: {self.window.window_text()}")
                return True
            except Exception as e:
                last_err = e
                time.sleep(2)
        safe_print(f"[FAIL] 未能按 hwnd 连接 Forms 窗口: {last_err}")
        return False

    def type_text(self, text: str, into=None):
        if into is not None:
            ctrl = self.window.child_window(**into)
            ctrl.set_focus()
            ctrl.type_keys(text, with_spaces=True)
        else:
            self.window.type_keys(text, with_spaces=True)
        safe_print(f"[Forms] 键入: {text}")

    def click_button(self, label: str):
        btn = self.window.child_window(title=label, control_type="Button")
        btn.click()
        safe_print(f"[Forms] 点击按钮: {label}")

    def select_menu(self, path: str):
        item = self.window.menu_select(path if "->" in path else path)
        safe_print(f"[Forms] 选择菜单: {path}")
        return item

    def get_edit_text(self, index: int = 0):
        edits = self.window.child_windows(control_type="Edit")
        if index < len(edits):
            val = edits[index].window_text()
            safe_print(f"[Forms] 读取字段[{index}]: {val}")
            return val
        safe_print(f"[WARN] 未找到第 {index} 个编辑框")
        return None

    def screenshot(self, path: str):
        try:
            self.window.capture_as_image().save(path)
            safe_print(f"[Forms] 截图已保存: {path}")
        except Exception as e:
            safe_print(f"[WARN] 截图失败: {e}")


# ══════════════════════════════════════════════════════════════════════
# 九、端到端：登录 -> 职责 -> 功能 -> 拉起 Forms
# ══════════════════════════════════════════════════════════════════════
def open_function(resp_name: str, func_name: str,
                  visible: bool = True, timeout: int = 150,
                  shot_path: str = "", close_ie: bool = False,
                  reuse_existing: bool = True):
    """
    端到端：登录 -> 读职责功能 -> 拿 launchForm URL -> 自开 IE 窗口加载 Forms
            -> 等 Forms 窗口 -> 返回 FormsApp。
    """
    ie = open_and_login(visible=visible, lang="ZHS")
    if ie is None:
        return None
    try:
        if not is_logged_in(ie):
            _log(f"[FAIL] 登录失败（title={page_title(ie)!r}）")
            return None

        before = snapshot_forms_windows()
        ie_before = snapshot_ie_windows()
        _log(f"[导航] 当前已有 Forms 窗口 {len(before)} 个")

        if reuse_existing and before:
            hwnd = list(before.keys())[-1]
            _log(f"[导航] 复用已打开的 Forms 窗口: hwnd={hwnd} "
                 f"title={before[hwnd]!r}")
            app = FormsApp()
            if not app.connect_by_hwnd(hwnd):
                return None
            try:
                app.window.set_focus()
            except Exception:
                pass
            if shot_path:
                app.screenshot(shot_path)
            return app

        try:
            if not expand_responsibility(ie, resp_name):
                return None
        except IeBroken as e:
            _log(f"[导航] IE 实例损坏（{e}），重建实例并重新登录后重试")
            close_our_instances()
            ie = open_and_login(visible=visible, lang="ZHS")
            if ie is None or not is_logged_in(ie):
                _log("[FAIL] 重建后仍无法登录")
                return None
            if not expand_responsibility(ie, resp_name):
                return None

        url = read_function_url(ie, func_name, resp_name=resp_name)
        if url is None:
            funcs = [f["name"] for f in list_functions(ie, resp_name=resp_name)]
            _log(f"[FAIL] 职责下未找到功能: {func_name}")
            _log(f"[提示] 该职责可用功能: {funcs}")
            return None
        _log(f"[导航] 功能「{func_name}」launchForm URL: {url[:180]}")

        ie2 = open_forms_window(url, visible=visible)
        if ie2 is None:
            return None

        time.sleep(3)
        new_ie = {h: t for h, t in snapshot_ie_windows().items()
                  if h not in ie_before}
        if new_ie:
            register_hwnds(list(new_ie.keys()))
            _log(f"[登记] 衍生 IE 载体窗口 {len(new_ie)} 个: "
                 f"{list(new_ie.values())[:2]}")

        hit = wait_new_forms_window(before, timeout=timeout)
        if not hit:
            now = snapshot_forms_windows()
            if now:
                hwnd = list(now.keys())[-1]
                _log(f"[WARN] 未出现新 Forms 窗口，复用已有窗口 hwnd={hwnd}")
                hit = (hwnd, now[hwnd])
            else:
                _log(f"[FAIL] {timeout}s 内未出现新 Forms 窗口"
                     "（请检查 IE 弹出的 Java 安全提示/证书确认框）")
                return None
        hwnd, title = hit
        _log(f"[OK] Oracle Forms 窗口已拉起: hwnd={hwnd} title={title!r}")

        app = FormsApp()
        if not app.connect_by_hwnd(hwnd):
            return None

        if shot_path:
            app.screenshot(shot_path)
        return app
    finally:
        _log("[导航] 流程结束（IE/Forms 仍开着，归调用方收口）")


# ══════════════════════════════════════════════════════════════════════
# 十、CLI 入口
# ══════════════════════════════════════════════════════════════════════
def _cmd_setup():
    interactive_setup()


def _cmd_check():
    pw = get_erp_password()
    if pw is None:
        safe_print("[FAIL] 未找到 ERP 密码文件，请先运行 erp.py setup")
        sys.exit(2)
    if pw:
        safe_print(f"[OK] ERP 密码可正常解密（长度 {len(pw)}）")
        sys.exit(0)
    safe_print("[FAIL] 解密为空")
    sys.exit(2)


def _cmd_login():
    keep = "--keep" in sys.argv or "--keep-ie" in sys.argv
    lang = "" if "--en" in sys.argv else "ZHS"

    # 纯 HTTP 无 COM 路径：不碰 IE / iexplore.exe，360 运行时也能登录。
    if "--http" in sys.argv or "--no-com" in sys.argv:
        import erp_jws
        _log("[HTTP] 使用纯 HTTP 登录（无 IE COM，不受 360 内核驱动影响）...")
        try:
            op, _jar, home_url = erp_jws.login()
            _log(f"[HTTP] [OK] 已登录 {ERP_USERNAME} -> {home_url[:70]}")
            _log(f"MEDIA:（无浏览器窗口，纯 HTTP 会话）")
            if not keep:
                erp_jws.logout(op)
            sys.exit(0)
        except Exception as e:
            _log(f"[HTTP] [FAIL] 纯 HTTP 登录失败: {e}")
            sys.exit(1)

    ie = open_and_login(visible=True, lang=lang)
    if ie is None:
        sys.exit(1)
    try:
        shot = os.path.join(SHOT_DIR, "ie11_login_success.png")
        shot_ok = screenshot_ie(ie, shot)
        _log(f"[IE11] 最终 title={page_title(ie)!r}")
        _log(f"[IE11] 页面文本片段: {body_text(ie)[:200]!r}")
        rc = 0 if is_logged_in(ie) else 2
        if shot_ok and os.path.exists(shot):
            _log(f"[IE11] 截图: {os.path.abspath(shot)}")
            _log(f"MEDIA:{os.path.abspath(shot)}")
        sys.exit(rc)
    finally:
        if not keep:
            close_all(logout=True)
        else:
            _log("[IE11] 完成（IE 窗口按 --keep 保留；退出时跑 erp.py logout 收口）")


def _cmd_logout():
    if "--no-close" in sys.argv:
        ok = logout_ebs()
        sys.exit(0 if ok else 2)
    closed = close_all(logout=True)
    sys.exit(0 if closed >= 0 else 2)


def _cmd_open_forms(resp: str, func: str):
    shot = os.path.join(SHOT_DIR, "forms_window.png")
    keep = "--keep-ie" in sys.argv or "--keep" in sys.argv

    # 纯 HTTP + javaws 无 COM 路径：HTTP 登录 → 抓 applet → JNLP → javaws 拉 Forms。
    if "--http" in sys.argv or "--no-com" in sys.argv:
        import erp_jws
        import erp_navigator
        _log("[HTTP] 纯 HTTP 登录 + 本地 javaws 拉 Forms（无 IE COM）...")
        try:
            op, _jar, home_url = erp_jws.login()
            _page, params, jars = erp_jws.fetch_applet(op)
            jp = erp_jws.build_jnlp(params, jars)
            _log(f"[HTTP] JNLP 已生成 {jp}（{len(params)} 参数 / {len(jars)} jar）")
            before = set(erp_navigator.snapshot_forms_windows())
            erp_jws.launch(jp)
            hwnd, title = erp_jws.wait_applet(before, timeout=180)
            if hwnd:
                _log(f"[HTTP] [OK] Forms 窗口 hwnd={hwnd} title={title}")
                _log(f"MEDIA:{os.path.normpath(shot)}")
                if not keep:
                    erp_jws.logout(op)
                sys.exit(0)
            _log("[HTTP] [FAIL] Forms 窗口未拉起（erp2 Forms 服务器 DNS/端口可能不通）")
            if not keep:
                erp_jws.logout(op)
            sys.exit(4)
        except Exception as e:
            _log(f"[HTTP] [FAIL] {e}")
            sys.exit(4)

    if not func:
        ie = open_and_login(visible=True, lang="ZHS")
        if ie is None or not is_logged_in(ie):
            safe_print("[FAIL] 登录失败")
            sys.exit(2)
        if not expand_responsibility(ie, resp):
            sys.exit(3)
        funcs = list_functions(ie, resp_name=resp)
        safe_print(f"职责「{resp}」下共 {len(funcs)} 个功能:")
        for f in funcs:
            safe_print(f"  - {f['name']}")
        safe_print("[提示] 用 erp.py open-forms <职责名> <功能名> 拉起对应 Forms")
        close_all(logout=True)
        return

    app = open_function(resp, func, timeout=150, shot_path=shot, close_ie=not keep)
    try:
        if app is None:
            safe_print("[FAIL] Forms 拉起失败，详见 logs/erp.log")
            sys.exit(4)
        safe_print("[OK] Forms 已就绪，可用 erp.FormsApp 驱动（键盘/坐标/菜单）")
        safe_print(f"MEDIA:{os.path.normpath(shot)}")
    finally:
        if not keep:
            close_all(logout=True)


def main():
    args = sys.argv[1:]
    if not args:
        safe_print("用法: erp.py {setup|check|login|logout|list-funcs <职责名>|"
                   "open-forms <职责名> [功能名]}")
        safe_print("  login                           登录 ERP（结束注销+关 IE；--keep 保留）")
        safe_print("  login --http                    纯 HTTP 登录（无 IE COM，360 运行时也能用）")
        safe_print("  open-forms <职责> <功能>        登录并拉起 Oracle Forms")
        safe_print("  open-forms <职责> <功能> --http 纯 HTTP + javaws 拉 Forms（无 IE COM）")
        safe_print("  list-funcs <职责>               列出职责下全部功能")
        safe_print("  logout                          注销 EBS + 关闭登记的 IE")
        safe_print("  setup / check                   设置 / 校验加密密码")
        safe_print("")
        safe_print("  提示：360 运行时会拦截 IE 内核（iexplore.exe 起不来），IE 路径报 E_NOINTERFACE。")
        safe_print("        此时请加 --http 走纯 HTTP 无 COM 路径（登录已实测可用；")
        safe_print("        Forms 需 erp2 Forms 服务器网络可达）。")
        sys.exit(1)
    cmd = args[0]
    if cmd == "setup":
        _cmd_setup()
    elif cmd == "check":
        _cmd_check()
    elif cmd == "login":
        _cmd_login()
    elif cmd in ("logout", "close"):
        _cmd_logout()
    elif cmd in ("open-forms", "list-funcs"):
        resp = args[1] if len(args) > 1 else ""
        if not resp:
            safe_print("[FAIL] 请提供职责名称: erp.py open-forms "
                       "\"PO,SANYO合肥三洋物料计划员\" [功能名]")
            sys.exit(1)
        func = args[2] if len(args) > 2 else ""
        _cmd_open_forms(resp, func)
    else:
        safe_print(f"[FAIL] 未知命令: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
