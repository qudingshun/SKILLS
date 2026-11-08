#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_login - 登录惠而浦 EBS（OA Framework 首页）

流程：
  1. 启动浏览器（默认 360 浏览器，见 erp_common.create_browser）
  2. 打开 EBS 首页；若跳到登录页则填 账号/密码 并提交
  3. 等待进入主页（出现“主页/Navigator/职责”等标志）
  4. 保存浏览器状态（cookies），下次免登录（12h 内）

退出码：
  0 = 登录成功
  1 = 失败（含 TLS 握手失败、超时、账号密码错误）
"""
import asyncio
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from erp_common import (
    ERP_HOME_URL, ERP_USERNAME, safe_print, create_browser,
    get_erp_password, save_storage_state, load_storage_state, wait_settled,
)

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs", "erp.log")

# 360 浏览器候选路径（自动回退用）
_360_CANDIDATES = [
    r"C:\Users\qudin\AppData\Roaming\360se6\Application\360se.exe",
    r"C:\Program Files (x86)\360\360se6\Application\360se.exe",
    r"C:\Program Files\360\360se6\Application\360se.exe",
]


def _log(msg):
    safe_print(msg)
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass


async def _is_logged_in(page) -> bool:
    """判断是否已经进入 EBS 主页（而非登录页）"""
    try:
        # 登录页通常没有这些主页特征（EBS 主页实际是英文界面）
        for sel in [
            "text=Logged In As", "text=Main Menu", "text=Worklist",
            "text=Oracle Applications Home Page",
            "text=Navigator", "text=职责", "text=主页", "text=Responsibilities",
            "#HomePG", "img[alt*='Oracle Applications']",
        ]:
            try:
                if await page.locator(sel).first.count() > 0:
                    return True
            except Exception:
                pass
        # 若页面里出现密码输入框，则仍在登录页
        pw = page.locator("input[type=password]")
        if await pw.count() > 0:
            return False
        return False
    except Exception:
        return False


async def _select_language_zh(page) -> bool:
    """若登录页有“简体中文”语言入口（该 EBS SSO 是 Vue 定制登录页，语言选项藏在
    display:none 的下拉 div.se-imt-entrance-lang 里），强制展开并点选“简体中文”。

    返回是否执行了切换动作。页面会随之重载（语言生效）。
    """
    try:
        # 该 SSO 页的语言组件是异步挂载的，先等它出现
        try:
            await page.wait_for_selector(".se-imt-entrance-lang", state="attached", timeout=20000)
        except Exception:
            # 也兼容直接用文本定位
            try:
                await page.wait_for_selector("text=简体中文", timeout=8000)
            except Exception:
                _log("[登录] 超时未找到语言组件，跳过切换")
                return False
        ok = await page.evaluate(
            """() => {
                const box = document.querySelector('.se-imt-entrance-lang');
                if (!box) return false;
                box.style.display = 'block';   // 强制展开隐藏的下拉
                const items = Array.from(box.querySelectorAll('li, p'));
                const zh = items.find(e => e.textContent.trim().includes('简体中文'));
                if (!zh) return false;
                const target = zh.closest('li') || zh;   // 点选项容器，确保触发 Vue @click
                target.click();
                return true;
            }"""
        )
        if ok:
            _log("[登录] 已选择“简体中文”，等待页面重载...")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=20000)
            except Exception:
                pass
            await wait_settled(page, timeout=10)
            # 兜底：设置隐藏语言字段，确保提交时带上 ZHS
            try:
                await page.evaluate(
                    "() => { const f = document.querySelector('input[name=_ssoLangCode]');"
                    " if (f) f.value = 'ZHS'; }"
                )
            except Exception:
                pass
            return True
        else:
            _log("[登录] 未发现语言下拉(.se-imt-entrance-lang)，跳过切换")
    except Exception as e:
        _log(f"[登录] 切换语言失败(忽略继续): {e}")
    return False


async def do_login_fill(page, password: str) -> bool:
    """在已打开的页面上填写并提交登录表单，等待进入主页。返回是否成功。"""
    # 先尝试切到简体中文（切换后页面可能重载，所以后面要重新定位控件）
    await _select_language_zh(page)

    # 重新定位登录表单（精确选择器优先，usernameField / passwordField）
    user_field = page.locator("input[name=usernameField]").first
    if await user_field.count() == 0:
        user_field = page.locator("input[type=text]").first
    pw = page.locator("input[name=passwordField]").first
    if await pw.count() == 0:
        pw = page.locator("input[type=password]").first

    if await pw.count() == 0:
        _log("[FAIL] 未检测到登录表单（也无主页特征），页面结构可能已变")
        await page.screenshot(path=os.path.join(os.path.dirname(LOG_FILE), "login_debug.png"))
        return False

    _log("[登录] 填写账号...")
    await user_field.fill(ERP_USERNAME)
    await pw.first.fill(password)
    _log("[登录] 提交登录...")
    clicked = False
    for btn in ["button:has-text('登录')", "button:has-text('Login')",
                "input[name=SubmitButton]", "input[type=submit]",
                "#SubmitButton", "img[alt*=Login]", "img[alt*=登录]"]:
        try:
            if await page.locator(btn).first.count() > 0:
                await page.locator(btn).first.click()
                clicked = True
                break
        except Exception:
            pass
    if not clicked:
        await pw.first.press("Enter")

    try:
        await page.wait_for_function(
            """() => {
                const t = document.body ? document.body.innerText : '';
                return /主页|Navigator|职责|Responsibilities|Oracle Applications/i.test(t)
                    && !document.querySelector('input[type=password]');
            }""",
            timeout=30000,
        )
        _log("[OK] 登录成功，已进入 EBS 主页")
        return True
    except Exception:
        _log("[FAIL] 登录后未检测到主页，可能账号密码错误或需额外验证")
        await page.screenshot(path=os.path.join(os.path.dirname(LOG_FILE), "login_debug.png"))
        return False


def _find_360_exe():
    for p in _360_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


async def _close_browser(p, browser):
    try:
        await browser.close()
    except Exception:
        pass
    try:
        await p.stop()
    except Exception:
        pass


async def _open_erp(headless: bool = False, fresh: bool = False):
    """创建浏览器并打开 ERP 首页。

    默认用 Edge（与其他技能一致）。

    ⚠️ 360 回退默认关闭（用户明确要求：不要把浏览器开到 360 上）。
    只有显式设置 WP_ENABLE_360=1 且本机存在 360 浏览器时才会回退。
    实际可用路径是 IE11（erp_ops.py login-ie11），本 Playwright 路径仅作备用。

    fresh=True 时，打开后先清除当前源点的 cookie，强制回到登录页
    （用于重新走“登录/语言切换”流程，如验证简体中文切换）。

    返回 (playwright, browser, context, page)。
    """
    async def _try_open():
        p, browser, context, page = await create_browser(headless=headless)
        if not fresh:
            await load_storage_state(context)
        await page.goto(ERP_HOME_URL, wait_until="domcontentloaded", timeout=45000)
        return p, browser, context, page

    try:
        return await _try_open()
    except Exception as e:
        err = str(e)
        ssl_fail = ("SSL_VERSION_OR_CIPHER_MISMATCH" in err or "ERR_SSL" in err
                    or "ERR_CONNECTION" in err)
        # 360 回退默认禁用：须显式 WP_ENABLE_360=1 才启用
        enable_360 = os.environ.get("WP_ENABLE_360", "0").strip() == "1"
        if not ssl_fail or not enable_360:
            if ssl_fail:
                _log("[提示] Edge 与该服务器 TLS 握手失败（服务器仅支持过时 TLS）。"
                     "360 回退已默认关闭；请改用 IE11 路径：erp_ops.py login-ie11")
            raise
        exe = _find_360_exe()
        if not exe:
            raise
        _log("[WARN] 已显式启用 360 回退（WP_ENABLE_360=1）")
        os.environ["WP_BROWSER_EXE"] = exe
        return await _try_open()


async def _force_login_page(page, context):
    """清除当前源点的 cookie，强制回到登录页（fresh 模式用）。"""
    try:
        origin = f"{urlparse(page.url).scheme}://{urlparse(page.url).netloc}"
        cdp = await context.new_cdp_session(page)
        await cdp.send("Storage.clearDataForOrigin",
                       {"origin": origin, "storageTypes": "cookies"})
        _log(f"[fresh] 已清除 {origin} 的 cookie，强制回登录页")
    except Exception as e:
        _log(f"[fresh] 清 cookie 失败(忽略): {e}")
    await page.goto(ERP_HOME_URL, wait_until="domcontentloaded", timeout=45000)
    await wait_settled(page, timeout=15)


async def login(headless: bool = False, save_state: bool = True,
                fresh: bool = False) -> int:
    password = get_erp_password()
    if not password:
        _log("[FAIL] 未找到 ERP 密码，请先运行 erp_secure_config.py 设置")
        return 1

    p, browser, context, page = await _open_erp(headless=headless, fresh=fresh)
    try:
        if fresh:
            await _force_login_page(page, context)
        else:
            await wait_settled(page, timeout=20)

        # 是否已登录（cookie 复用）
        if await _is_logged_in(page):
            _log("[OK] 已处于登录态（cookie 复用）")
            if save_state:
                await save_storage_state(context)
            return 0

        ok = await do_login_fill(page, password)
        if not ok:
            return 1
        if save_state:
            await save_storage_state(context)
        return 0
    finally:
        await _close_browser(p, browser)


def main():
    headless = "--headless" in sys.argv
    fresh = "--fresh" in sys.argv
    rc = asyncio.run(login(headless=headless, fresh=fresh))
    sys.exit(rc)


if __name__ == "__main__":
    main()
