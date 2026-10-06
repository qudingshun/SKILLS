"""
whirlpool_common - 惠而浦报表下载工具公共模块

共享函数：浏览器创建、密码编解码、安全输出、依赖检查。
"""
import asyncio
import base64
import hashlib
import json
import os
import sys
from datetime import datetime

from playwright.async_api import async_playwright


# ── 浏览器状态持久化 ────────────────────────────────────────────────

STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(STORAGE_DIR, exist_ok=True)
STORAGE_FILE_SCM = os.path.join(STORAGE_DIR, "scm_state.json")


async def save_storage_state(context, state_path: str):
    """保存浏览器状态（cookies + localStorage）到文件"""
    try:
        state = await context.storage_state()
        state["saved_at"] = datetime.now().isoformat()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        safe_print(f"  [状态] 已保存浏览器状态 ({len(state.get('cookies',[]))} cookies)")
        return True
    except Exception as e:
        safe_print(f"  [状态] 保存失败: {e}")
        return False


async def load_storage_state(context, state_path: str) -> bool:
    """从文件恢复浏览器状态"""
    try:
        if not os.path.exists(state_path):
            return False
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        # 检查是否过期
        saved_at = state.get("saved_at", "")
        if saved_at:
            try:
                dt = datetime.fromisoformat(saved_at)
                elapsed = (datetime.now() - dt).total_seconds() / 3600
                if elapsed > 12:
                    safe_print(f"  [状态] 已过期 ({elapsed:.0f}h > 12h)")
                    return False
            except Exception:
                pass
        # 只恢复 cookies（其他状态在浏览器重新打开后可能无效）
        cookies = state.get("cookies", [])
        if not cookies:
            return False
        await context.add_cookies(cookies)
        safe_print(f"  [状态] 已恢复 {len(cookies)} cookies")
        return True
    except Exception as e:
        safe_print(f"  [状态] 加载失败: {e}")
        return False


# ── 智能页面等待 ──────────────────────────────────────────────────────# ── 智能页面等待 ──────────────────────────────────────────────────────

async def wait_for_page_settled(page, timeout=15, min_idle=1.0):
    """等待页面静止，超时不抛异常"""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout * 1000)
    except Exception:
        pass
    if min_idle > 0:
        await asyncio.sleep(min_idle)


# ── 计时器 ────────────────────────────────────────────────────────────

class Stopwatch:
    """阶段计时器，用于调试性能"""
    def __init__(self, label=""):
        self.label = label
        self.start = datetime.now()
        self.last_mark = self.start

    def mark(self, name=""):
        now = datetime.now()
        total = int((now - self.start).total_seconds())
        since_last = int((now - self.last_mark).total_seconds())
        prefix = f"[{self.label}] " if self.label else ""
        safe_print(f"  [计时] {prefix}{name}: +{since_last}s (累计{total}s)")
        self.last_mark = now
        return total


# ── 安全输出（解决 GBK 控制台报 UnicodeEncodeError） ──────────────────

# 常见 Emoji / 特殊符号 → 安全文本映射
_UNICODE_SAFE_MAP = {
    "\u2713": "[OK]",     # ✓
    "\u2714": "[OK]",     # ✔
    "\u2716": "[X]",      # ✖
    "\u2705": "[OK]",     # ✅
    "\u274c": "[X]",      # ❌
    "\u23f3": "[WAIT]",   # ⏳
    "\u26a0": "[WARN]",   # ⚠
    "\ufe0f": "",         # 变体选择符
    "\u279c": "->",       # ➜
}


def safe_print(*args, sep=" ", **kwargs):
    """打印时自动过滤不可编码的 Unicode 字符（针对 GBK 控制台）"""
    cleaned = []
    encoding = sys.stdout.encoding or "utf-8"
    for a in args:
        s = str(a)
        try:
            s.encode(encoding)
            cleaned.append(s)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # 替换已知特殊符号
            for char, repl in _UNICODE_SAFE_MAP.items():
                s = s.replace(char, repl)
            # 剩余不可编码字符替换为 ?
            s = s.encode(encoding, errors="replace").decode(encoding, errors="replace")
            cleaned.append(s)
    print(*cleaned, sep=sep, **kwargs)


# ── 密码编解码 ────────────────────────────────────────────────────────

def _get_local_key():
    seed = f"{os.getenv('USERNAME', '')}|{os.getenv('COMPUTERNAME', '')}|BOM_CFG_V1"
    return hashlib.sha256(seed.encode("utf-8")).digest()


def decode_local_password(encoded_text):
    if not encoded_text:
        return ""
    if not str(encoded_text).startswith("enc1:"):
        return str(encoded_text)
    try:
        payload = str(encoded_text)[5:]
        key = _get_local_key()
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        plain = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw)])
        return plain.decode("utf-8")
    except Exception as e:
        safe_print(f"警告: 密码解码失败: {e}")
        return ""


# ── 浏览器创建 ────────────────────────────────────────────────────────

async def create_browser(headless: bool = True):
    # 支持环境变量 WP_HEADLESS 覆盖（run.js --visible 时设为 "0"）
    if str(os.environ.get("WP_HEADLESS", "")).strip() == "0":
        headless = False
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        channel="msedge", headless=headless,
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox",
              "--ignore-certificate-errors", "--disable-web-security",
              "--disable-gpu", "--disable-software-rasterizer",
              "--disable-dev-shm-usage", "--js-flags=--max-old-space-size=512"],
    )
    context = await browser.new_context(
        ignore_https_errors=True, viewport={"width": 1280, "height": 800},
        locale="zh-CN", timezone_id="Asia/Shanghai", accept_downloads=True,
    )
    page = await context.new_page()
    return p, browser, context, page


# ── 依赖检查 ──────────────────────────────────────────────────────────

def check_dependencies(modules: list) -> bool:
    missing = []
    for m in modules:
        try:
            __import__(m)
        except ImportError:
            missing.append(m)
    if missing:
        safe_print("缺少依赖，请安装:")
        safe_print(f"  pip install {' '.join(missing)}")
        return False
    return True


# ── 结束计时器 ────────────────────────────────────────────────────────

def format_elapsed(start) -> str:
    elapsed = datetime.now() - start
    total_sec = int(elapsed.total_seconds())
    return f"{total_sec // 60}分{total_sec % 60}秒"
