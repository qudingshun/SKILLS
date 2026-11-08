"""
erp_common - WHP ERP 公共模块

共享函数：浏览器创建（支持 360 浏览器）、storage 状态持久化、安全输出、
加密密码读取、日志。
"""
import datetime
import json
import os
import sys

from playwright.async_api import async_playwright

# ── 路径 ────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(_BASE_DIR)
STORAGE_DIR = os.path.join(_BASE_DIR, ".cache")
os.makedirs(STORAGE_DIR, exist_ok=True)
STORAGE_FILE = os.path.join(STORAGE_DIR, "erp_state.json")

# 默认 ERP 入口（EBS OAF 首页）
ERP_HOME_URL = (
    "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp"
    "?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
    "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y"
    "&oapc=2&transactionid=1652645857&oas=BqTsZ_lSLwh9QeRE263_4g.."
)

# 默认账号（密码走加密存储，绝不在此写明文）
ERP_USERNAME = "hsa697"


# ── 安全输出 ────────────────────────────────────────────────────────────
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


# ── 加密密码读取 ─────────────────────────────────────────────────────────
def get_erp_password():
    """从加密存储读取 ERP 密码；未设置返回 None"""
    try:
        from erp_secure_config import SecurePasswordManager
    except ImportError:
        sys.path.insert(0, _BASE_DIR)
        from erp_secure_config import SecurePasswordManager
    mgr = SecurePasswordManager()
    return mgr.load_password("erp")


# ── storage 状态持久化（cookies，免重复登录） ───────────────────────────
async def save_storage_state(context, state_path: str = STORAGE_FILE):
    try:
        state = await context.storage_state()
        state["saved_at"] = datetime.datetime.now().isoformat()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        safe_print(f"  [状态] 已保存浏览器状态 ({len(state.get('cookies', []))} cookies)")
        return True
    except Exception as e:
        safe_print(f"  [状态] 保存失败: {e}")
        return False


async def load_storage_state(context, state_path: str = STORAGE_FILE) -> bool:
    try:
        if not os.path.exists(state_path):
            return False
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        saved_at = state.get("saved_at", "")
        if saved_at:
            try:
                dt = datetime.datetime.fromisoformat(saved_at)
                elapsed = (datetime.datetime.now() - dt).total_seconds() / 3600
                if elapsed > 12:
                    safe_print(f"  [状态] 已过期 ({elapsed:.0f}h > 12h)")
                    return False
            except Exception:
                pass
        cookies = state.get("cookies", [])
        if not cookies:
            return False
        await context.add_cookies(cookies)
        safe_print(f"  [状态] 已恢复 {len(cookies)} cookies")
        return True
    except Exception as e:
        safe_print(f"  [状态] 加载失败: {e}")
        return False


# ── 智能等待 ────────────────────────────────────────────────────────────
async def wait_settled(page, timeout=20, min_idle=1.0):
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout * 1000)
    except Exception:
        pass
    if min_idle > 0:
        await page.wait_for_timeout(int(min_idle * 1000))


# ── 浏览器创建 ──────────────────────────────────────────────────────────
async def create_browser(headless: bool = False):
    """
    创建浏览器。默认有头模式（Forms/Java 需要可见窗口）。

    浏览器选择（按优先级）：
      1. 环境变量 WP_BROWSER_EXE 指向的 exe
         -> 走 CDP 附加（仅当 Edge 无法握手该服务器时才需要）
      2. 否则用 msedge（Playwright channel，本仓库各技能统一做法）

    ⚠️ 360 浏览器默认禁用（用户要求：不要把浏览器开到 360 上）。
    若 WP_BROWSER_EXE 指向 360se.exe，必须同时设 WP_ENABLE_360=1 才会使用，
    否则忽略该变量、退回 msedge。实际可用路径是 IE11（erp_ie11.py）。
    """
    browser_exe = os.environ.get("WP_BROWSER_EXE", "").strip()
    # 360 默认禁用：未显式开启时，忽略指向 360 的 WP_BROWSER_EXE
    if browser_exe and "360" in os.path.basename(browser_exe).lower():
        if os.environ.get("WP_ENABLE_360", "0").strip() != "1":
            safe_print("  [浏览器] 检测到 360 路径但 360 已默认禁用"
                       "（需 WP_ENABLE_360=1 才启用），改用 msedge")
            browser_exe = ""
    p = await async_playwright().start()

    if browser_exe and os.path.exists(browser_exe):
        # 方式 A：CDP 附加自定义浏览器（如 360）。复用其证书信任/代理/老 TLS 能力。
        # 360 作为独立 Chromium 分支无法被 Playwright 直接 launch，只能走 CDP。
        safe_print(f"  [浏览器] 通过 CDP 附加自定义浏览器: {browser_exe}")
        browser = await _launch_and_connect_cdp(p, browser_exe, headless)
        # CDP 附加后，优先复用其默认 context（继承 profile 的 cookies/代理/证书信任）
        if browser.contexts:
            context = browser.contexts[0]
            safe_print("  [浏览器] 复用默认 context")
            page = await context.new_page()
            return p, browser, context, page
        context = await browser.new_context(
            ignore_https_errors=True,
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            accept_downloads=True,
        )
        page = await context.new_page()
        return p, browser, context, page

    # 方式 B（默认）：Edge（msedge），Playwright channel 方式，与其他技能一致
    safe_print("  [浏览器] 使用 msedge (Playwright channel)")
    launch_kwargs = dict(
        channel="msedge",
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--ignore-certificate-errors",
            "--ssl-version-min=tls1",          # 关键：服务器只认老 TLS(1.0/1.1)
            "--disable-web-security",
            "--allow-insecure-localhost",
            "--disable-gpu",
            "--disable-dev-shm-usage",
        ],
    )
    try:
        browser = await p.chromium.launch(**launch_kwargs)
    except Exception as e:
        safe_print(f"  [WARN] msedge 启动失败: {e}，尝试系统 chromium")
        launch_kwargs.pop("channel", None)
        browser = await p.chromium.launch(**launch_kwargs)

    context = await browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1366, "height": 768},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        accept_downloads=True,
    )
    page = await context.new_page()
    return p, browser, context, page


# ── 360 浏览器 CDP 附加 ─────────────────────────────────────────────────
def _launch_360_cdp(exe: str, port: int, headless: bool):
    """以子进程方式启动 360 浏览器并开启远程调试端口，返回 Popen。"""
    import subprocess
    args = [
        exe,
        f"--remote-debugging-port={port}",
        "--no-sandbox",
        "--ignore-certificate-errors",   # 容忍自签/老证书
        "--ssl-version-min=tls1",        # 关键：服务器只认老 TLS(1.0/1.1)
        "--disable-web-security",
        "--allow-insecure-localhost",
        "--disable-gpu",
    ]
    if headless:
        args.append("--headless=new")
    # 不指定 --user-data-dir 以复用 360 默认配置（证书信任/代理/VPN）
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


async def _launch_and_connect_cdp(p, exe: str, headless: bool):
    import asyncio
    import urllib.request
    last_err = None
    for port in range(9222, 9228):
        proc = _launch_360_cdp(exe, port, headless)
        # 等待 DevTools 端点就绪。
        # 注意：360se.exe 是启动器，会拉起真正的浏览器进程后自己退出（code=24），
        # 所以"启动器进程退出"不算失败，必须坚持轮询端口。
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",
                                            timeout=1) as r:
                    if r.status == 200:
                        safe_print(f"  [CDP] 360 调试端口就绪: {port}")
                        browser = await p.chromium.connect_over_cdp(
                            f"http://127.0.0.1:{port}")
                        return browser
            except Exception as e:
                last_err = e
            await asyncio.sleep(1)
        # 该端口没起来，杀掉重试下一个端口
        try:
            proc.terminate()
        except Exception:
            pass
    safe_print(f"  [WARN] 360 浏览器 CDP 启动失败: {last_err}")
    raise RuntimeError("无法启动 360 浏览器远程调试端口")
