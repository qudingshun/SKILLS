"""
回货计划导入 & 发放工具（OpenClaw 技能版）
v2.2 — 直通批量导入模式

用法:
  python huihuo_scm.py --data "70C11099 2"                     # 单行
  python huihuo_scm.py --data "70C11099 2 售后配件"            # 单行+备注
  python huihuo_scm.py --data "70C11099 2, ABC 3 紧急补货"    # 多行
"""
import asyncio
import base64
import calendar
import datetime as _dt
import json
import logging
import os
import re
import sys
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path
from playwright.async_api import async_playwright

# ── WHP-scm-suite 共享核心引导 ──────────────────────────────
# 本脚本位于 <suite>/scripts/<module>/，套件根为上级两级目录
SUITE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(SUITE_DIR, "scripts"))
CONFIG_PATH = os.path.join(SUITE_DIR, "runtime_config.json")

from wh_core.secure_config import ConfigManager, SecurePasswordManager

# ═══════════════════════════════════════════════════════════
# 日志初始化：控制台 + 文件双写，自动轮转
# ═══════════════════════════════════════════════════════════
_LOG_DIR = Path(__file__).parent
_LOG_FILE = _LOG_DIR / "scm_huihuo.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        RotatingFileHandler(
            _LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=5,
            encoding="utf-8", delay=True,
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
_logger = logging.getLogger("scm_huihuo")

# Windows GBK 控制台兼容：将 stdout 切换到 UTF-8
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

SCM_URL = "https://scm.whirlpool-china.com:7580/websrm/"

# ============================================================
# 从 runtime_config.json 加载配置
# ============================================================
def _load_runtime_config():
    """从 runtime_config.json 读取 SCM 配置，优先使用 AES-256 加密密码"""
    cfg = {"username": "your_username", "password": ""}
    project_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = CONFIG_PATH
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            scm = data.get("scm", {})
            if scm.get("username"):
                cfg["username"] = scm["username"]
        except Exception:
            pass

    # 优先从 AES-256 加密文件读取密码，回退到配置文件值
    try:
        config_manager = ConfigManager(config_path)
        secure_manager = SecurePasswordManager(config_manager)
        password = secure_manager.load_password("scm")
        if password:
            cfg["password"] = password
            return cfg
    except Exception:
        pass
    # 回退：从 runtime_config.json 读取
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            scm = data.get("scm", {})
            if scm.get("password"):
                cfg["password"] = scm["password"]
        except Exception:
            pass
    return cfg

_cfg = _load_runtime_config()
USERNAME = _cfg["username"]
PASSWORD = _cfg["password"]

# ============================================================
# 全局标志：记录是否已开始填写数据（用于决定异常时是否重试）
# ============================================================
_data_entry_started = False

# ============================================================
# 日志工具 & 摘要追踪
# ============================================================
_START_TIME = _dt.datetime.now()

def ts(msg="", level="info"):
    """带时间戳的日志输出（控制台 + 文件双写）"""
    if level == "warning":
        _logger.warning(msg)
    elif level == "error":
        _logger.error(msg)
    elif level == "debug":
        _logger.debug(msg)
    else:
        _logger.info(msg)

# 执行摘要，用于脚本末尾统一输出
SUMMARY = {
    "started": _START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
    "ended": None,
    "duration_s": None,
    "status": "unknown",
    "items": [],
}

def _add_item_summary(mat, qty, remark, import_ok, release_ok, release_error=""):
    SUMMARY["items"].append({
        "material": mat,
        "qty": qty,
        "remark": remark,
        "import": "OK" if import_ok else "FAIL",
        "release": "OK" if release_ok else ("SKIP" if import_ok else "-"),
        "release_error": release_error,
    })

def _print_summary():
    now = _dt.datetime.now()
    SUMMARY["ended"] = now.strftime("%Y-%m-%d %H:%M:%S")
    SUMMARY["duration_s"] = round((now - _START_TIME).total_seconds(), 1)
    # 写入日志文件（JSON 格式，方便 grep/jq 解析）
    _logger.info("=== SUMMARY (JSON) ===\n" + json.dumps(SUMMARY, ensure_ascii=False, indent=2))
    # 控制台格式化输出
    print()
    print("=" * 50)
    print("=== SUMMARY ===")
    print(f"  status:    {SUMMARY['status']}")
    print(f"  started:   {SUMMARY['started']}")
    print(f"  ended:     {SUMMARY['ended']}")
    print(f"  duration:  {SUMMARY['duration_s']}s")
    print(f"  items:     {len(SUMMARY['items'])}")
    ok_count = sum(1 for i in SUMMARY['items'] if i['release'] == 'OK')
    fail_count = sum(1 for i in SUMMARY['items'] if i['release'] == 'FAIL' or i['import'] == 'FAIL')
    print(f"  success:   {ok_count}  failed: {fail_count}")
    for i, item in enumerate(SUMMARY["items"], 1):
        print(f"    [{i}] {item['material']} x{item['qty']}" + (f" ({item['remark']})" if item["remark"] else ""))
        print(f"         import={item['import']}  release={item['release']}", end="")
        if item.get("release_error"):
            print(f"  [WARN] {item['release_error'][:100]}")
        else:
            print()
    print("=" * 50)


# ============================================================
# 登录函数
# ============================================================

async def is_logged_in(page) -> bool:
    try:
        has_login_form = await page.evaluate("""() => {
            var u = document.querySelector('#username');
            var p = document.querySelector('input[type="password"]');
            var k = document.querySelector('#kaptcha');
            if (p || k) return true;
            if (u && u.offsetParent !== null) return true;
            return false;
        }""")
        return not has_login_form
    except Exception:
        return False


async def recognize_captcha(page):
    try:
        b64 = await page.evaluate("""async () => {
            var img = document.querySelector('#changeCode');
            if (!img) return null;
            try {
                var r = await fetch(img.src + '?' + Date.now(), {cache: 'no-cache'});
                var b = await r.blob();
                return new Promise(function(resolve) {
                    var reader = new FileReader();
                    reader.onloadend = function() { resolve(reader.result); };
                    reader.readAsDataURL(b);
                });
            } catch(e) { return null; }
        }""")
        if not b64 or ',' not in b64:
            return None
        img_bytes = base64.b64decode(b64.split(',')[1])
        try:
            import ddddocr
            ocr = ddddocr.DdddOcr(show_ad=False)
            result = ocr.classification(img_bytes)
            result = result.strip() if result else ""
            if result and len(result) >= 3 and result.isascii():
                return result
        except ImportError:
            print(" [OCR] 未安装 ddddocr")
        except Exception:
            pass
        return None
    except Exception:
        return None


async def login_scm(page, username, password):
    for login_attempt in range(1, 4):
        print(f" [登录] 第 {login_attempt}/3 次尝试...")

        await page.goto(SCM_URL, timeout=120000, wait_until="domcontentloaded")
        await asyncio.sleep(0.8)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(1)

        if await is_logged_in(page):
            print(" [登录] 已登录")
            return True

        try:
            el = await page.wait_for_selector("#username", timeout=10000)
            await el.click(); await el.fill(""); await el.fill(username)
        except Exception:
            print(" [FAIL] 用户名框"); return False

        try:
            el = await page.wait_for_selector("#password", timeout=5000)
            await el.fill(""); await el.fill(password)
        except Exception:
            print(" [FAIL] 密码框"); return False

        try:
            await page.wait_for_selector("#kaptcha", timeout=5000)
        except Exception:
            print(" [FAIL] 验证码框"); return False

        captcha = None
        for attempt in range(1, 4):
            if attempt > 1:
                try:
                    await page.locator("#changeCode").click(timeout=3000)
                    await asyncio.sleep(2)
                except Exception:
                    pass
            captcha = await recognize_captcha(page)
            if captcha:
                print(f" [登录] OCR: {captcha}")
                break

        if not captcha:
            print(f" [登录] OCR 识别失败，跳过本次尝试")
            continue

        el = await page.query_selector("#kaptcha")
        if el:
            await el.fill(""); await el.fill(captcha)

        for sel in ["input[name='CPCLogin']", ".sub_btn", "input[type='submit']"]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click(); break
            except Exception:
                continue
        else:
            await page.keyboard.press("Enter")

        await asyncio.sleep(1)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(0.8)

        if await is_logged_in(page):
            print(" [OK] 登录成功！")
            return True
        else:
            print(f" [FAIL] 登录失败（验证码可能错误）")

    print("\n [FAIL] 3次登录尝试均失败，请检查账号密码或网络")
    return False


# ============================================================
# 导航 & 工具
# ============================================================

async def nav_to(page, accordion_text, menu_text, button_text):
    await page.goto(SCM_URL, timeout=30000)
    await asyncio.sleep(0.8)
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    await asyncio.sleep(1)

    try:
        loc = page.locator(f"text={accordion_text}").first
        if await loc.is_visible(timeout=5000):
            await loc.click()
            await asyncio.sleep(0.8)
    except Exception:
        pass

    try:
        loc = page.locator(f"text={menu_text}").first
        if await loc.is_visible(timeout=5000):
            await loc.click()
            await asyncio.sleep(0.8)
    except Exception:
        print(f" [FAIL] 未找到: {menu_text}")
        return False

    try:
        popup = page.locator(".crisp_menu_list")
        await popup.wait_for(state="visible", timeout=8000)
        btn = page.locator(f'.crisp_menu_list button:has-text("{button_text}")').first
        await btn.wait_for(state="visible", timeout=5000)
        await btn.click()
        await asyncio.sleep(0.8)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(1)
        return True
    except Exception as e:
        print(f" [FAIL] {button_text}: {e}")
        return False


async def close_tab(page):
    for sel in [
        ".x-toolbar .x-btn:has-text('关闭')",
        "span.x-btn-inner:has-text('关闭')",
        "#button-1174",
    ]:
        try:
            loc = page.locator(sel)
            count = await loc.count()
            if count == 0:
                continue
            await (loc.last if count > 1 else loc.first).click(force=True, timeout=5000)
            return True
        except Exception:
            continue
    return False


async def check_session_alive(page):
    """会话存活检查：如掉线则自动重登"""
    try:
        alive = await is_logged_in(page)
        if not alive:
            print(" [WARN] SCM 会话已过期，尝试重新登录...")
            return await login_scm(page, USERNAME, PASSWORD)
        return True
    except Exception:
        print(" [WARN] 会话检查异常，尝试重新登录...")
        try:
            return await login_scm(page, USERNAME, PASSWORD)
        except Exception:
            return False


async def wait_loadmask(page, label="操作"):
    for i in range(120):
        loading = await page.evaluate("""() => {
            var m = document.querySelectorAll('[id^="loadmask-"]');
            for (var x of m) {
                if (x.classList.contains('x-mask') && x.style.display !== 'none') return true;
            }
            return false;
        }""")
        if not loading:
            print(f" [OK] {label} ~{i+1}s")
            return
        await asyncio.sleep(1)
    print(f" [WARN] {label} 超时")


# ============================================================
async def detect_dialog_error(page, action_label="操作"):
    """检测SCM弹窗，返回错误文本（有错误）或空字符串（无/普通弹窗）
    
    使用 Playwright 原生 locator 检测弹窗，避免 JS evaluate 注入风险。
    """
    dialog_text = ""
    try:
        # 尝试多个已知弹窗选择器
        dialog_selectors = [
            '.layui-layer-content',
            '.x-message-box .x-window-text',
            '.x-window-body',
            '.x-window-bwrap',
            '[class*="msgbox"] .x-window-body',
        ]
        all_texts = []
        for sel in dialog_selectors:
            try:
                elements = page.locator(sel)
                count = await elements.count()
                for idx in range(count):
                    el = elements.nth(idx)
                    if await el.is_visible(timeout=500):
                        text = (await el.inner_text()).strip()
                        if text:
                            # 标准化空白
                            text = ' '.join(text.split())
                            all_texts.append(text)
            except Exception:
                continue
        
        if all_texts:
            dialog_text = ' |~| '.join(all_texts)
    except Exception as e:
        print(f" [WARN] 弹窗检测异常: {e}")
        return ""

    if dialog_text:
        print(f" [{action_label}] 弹窗: {dialog_text[:200]}")
        if any(kw in dialog_text for kw in ["失败", "错误", "非法", "Error", "error", "异常", "操作失败", "请选择需要修改", "没有符合"]):
            print(f" [{action_label}] 弹窗含失败信息，中止")
            for sel in ['.layui-layer-btn1', 'a.layui-layer-btn1',
                        '.layui-layer-close', '.x-tool-close']:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        break
                except Exception:
                    continue
            return dialog_text.split('|~|')[0].strip()
    else:
        print(f" [{action_label}] 弹窗: (空/未检测到)")
    return ""


# 回货计划导入 — 新增行填数据
# ============================================================

_MATERIAL_RE = re.compile(r'^[A-Za-z0-9-]{3,25}$')

def _check_item(item):
    """快速检查单个物料格式，返回错误文本或空字符串"""
    mat_code = item[0] if len(item) >= 1 else ""
    qty_str = item[1] if len(item) >= 2 else ""
    if not mat_code or not mat_code.strip():
        return f"料号为空"
    if not _MATERIAL_RE.match(mat_code.strip().upper()):
        return f"料号格式异常: {mat_code}"
    if not qty_str or not qty_str.strip():
        return f"数量为空 ({mat_code})"
    try:
        q = int(qty_str.strip())
        if q <= 0:
            return f"数量必须为正整数: {qty_str}"
    except ValueError:
        return f"数量不是有效整数: '{qty_str}'"
    return ""


async def fill_cell_click_type(page, row_locator, column_id, text, tab=True):
    """点击单元格 → 三击全选 → type输入（支持 ExtJS 事件）"""
    try:
        cell = row_locator.locator(f'td[data-columnid="{column_id}"] .x-grid-cell-inner')
        if not await cell.is_visible(timeout=3000):
            return False

        await cell.click(force=True)
        await asyncio.sleep(0.2)
        await cell.click(click_count=3, force=True)
        await asyncio.sleep(0.15)
        await page.keyboard.press("Delete")
        await asyncio.sleep(0.1)
        await page.keyboard.type(text, delay=10)
        await asyncio.sleep(0.15)
        if tab:
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.3)
        return True
    except Exception as e:
        print(f" [WARN] {column_id}: {e}")
        try:
            await asyncio.sleep(0.15)
            await page.keyboard.press("Delete")
            await asyncio.sleep(0.1)
            await page.keyboard.type(text, delay=10)
            await asyncio.sleep(0.15)
            if tab:
                await page.keyboard.press("Tab")
                await asyncio.sleep(0.3)
            return True
        except:
            return False


async def fill_date_cell(page, row_locator, column_id, date_text):
    """日期单元格：点击激活 → JS原生设值 → Enter确认"""
    try:
        cell = row_locator.locator(f'td[data-columnid="{column_id}"] .x-grid-cell-inner')
        if not await cell.is_visible(timeout=3000):
            return False

        await cell.click(force=True)
        await asyncio.sleep(1)

        _safe_date = json.dumps(date_text)
        set_ok = await page.evaluate(f"""() => {{
            try {{
                var ed = document.querySelector('.x-grid-editor');
                if (!ed) return false;
                var inp = ed.querySelector('input');
                if (!inp) return false;
                var proto = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
                if (proto && proto.set) {{
                    proto.set.call(inp, {_safe_date});
                }} else {{
                    inp.value = {_safe_date};
                }}
                ['input','change','blur'].forEach(function(ev) {{
                    inp.dispatchEvent(new Event(ev, {{bubbles:true}}));
                }});
                return true;
            }} catch(e) {{ return false; }}
        }}""")

        if set_ok:
            await asyncio.sleep(0.3)
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.5)
            return True

        print(" [WARN] 日期编辑器未找到")
        return False
    except Exception as e:
        print(f" [WARN] 日期列: {e}")
        return False


async def fill_cell_search_popup(page, row_locator, column_id, search_text, search_tab=True):
    """网格单元格搜索弹窗：激活 → 点击搜索图标 → 搜关键字 → 选第一条 → 确定"""
    try:
        cell = row_locator.locator(f'td[data-columnid="{column_id}"] .x-grid-cell-inner')
        if not await cell.is_visible(timeout=3000):
            return False

        await cell.click(force=True)
        await asyncio.sleep(0.8)

        trigger = page.locator('.x-grid-editor .x-form-search-trigger, .x-grid-editor .x-trigger-index-0').first
        if await trigger.is_visible(timeout=3000):
            await trigger.click()
            await asyncio.sleep(0.8)
        else:
            trigger = page.locator('.x-form-search-trigger:visible').first
            if await trigger.is_visible(timeout=5000):
                await trigger.click()
                await asyncio.sleep(0.8)
            else:
                await page.keyboard.press("Alt+ArrowDown")
                await asyncio.sleep(1)

        search_input = page.locator(
            '.x-window:visible input.x-form-field, '
            '.x-layer:visible input.x-form-field'
        ).first
        if await search_input.is_visible(timeout=5000):
            await search_input.click()
            await asyncio.sleep(0.3)
            await search_input.fill(search_text)
            await asyncio.sleep(1)
        else:
            print(f" [WARN] 搜索弹窗输入框未找到")
            return False

        for sel in ['.x-window:visible .x-btn-inner:has-text("立即搜索")',
                    '.x-layer:visible .x-btn-inner:has-text("立即搜索")']:
            try:
                btn = page.locator(sel).first
                if await btn.is_visible(timeout=5000):
                    await btn.click(force=True)
                    await asyncio.sleep(0.8)
                    break
            except Exception:
                continue

        result = page.locator(
            '.x-window:visible .x-grid-cell-inner, '
            '.x-layer:visible .x-grid-cell-inner'
        ).first
        if await result.is_visible(timeout=8000):
            await result.click()
            await asyncio.sleep(1)
        else:
            print(f" [WARN] 搜索结果未找到")
            return False

        for sel in ['.x-window:visible .x-btn-inner:has-text("确定")',
                    '.x-layer:visible .x-btn-inner:has-text("确定")']:
            try:
                ok = page.locator(sel).first
                if await ok.is_visible(timeout=5000):
                    await ok.click(force=True)
                    await asyncio.sleep(1)
                    break
            except Exception:
                continue

        if search_tab:
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.5)
        return True
    except Exception as e:
        print(f" [WARN] 搜索弹窗 {column_id}: {e}")
        return False


async def import_single_item(page, item):
    """导入单行物料：新增→填6列→保存审核（用于逐条模式和批量模式的单元填充）"""
    global _data_entry_started
    _data_entry_started = True

    mat_code, qty = item[0], item[1]
    remarks = item[3] if len(item) >= 4 and item[3].strip() else ""

    date_str = item[2] if len(item) >= 3 and item[2].strip() else ""
    if date_str:
        m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', date_str)
        if m:
            date_str = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        else:
            print(f" [WARN] 日期格式异常: {date_str}，使用默认")
            date_str = ""
    if not date_str:
        today = date.today()
        last_day = calendar.monthrange(today.year, today.month)[1]
        date_str = f"{today.year}-{today.month:02d}-{last_day:02d}"
    print(f"  料号: {mat_code}  qty={qty}" + (f"  备注: {remarks}" if remarks else ""))
    print(f"  日期: {date_str}  组织: M03  工厂: 洗衣机三工厂")

    # 点击「增加明细」按钮（每行一条新记录）
    try:
        btn = page.locator('span.x-btn-inner:has-text("增加明细")').first
        if await btn.is_visible(timeout=3000):
            await btn.click(force=True)
            await asyncio.sleep(1)
        else:
            btn = page.locator('#button-2260')
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                await asyncio.sleep(1)
            else:
                btn = page.locator('span.x-btn-inner:has-text("新增")').first
                if await btn.is_visible(timeout=3000):
                    await btn.click(force=True)
                    await asyncio.sleep(1)
    except Exception as e:
        print(f" [FAIL] 新增: {e}")
        return False

    # 增加明细后找编辑器所在行（最可靠的方式）
    await asyncio.sleep(0.8)
    row = page.locator('.x-grid-row').filter(has=page.locator('.x-grid-editor')).first
    if not await row.is_visible(timeout=3000):
        # 备用：filter出所有数据行取最后一个
        row = page.locator('.x-grid-row').filter(has=page.locator('td[data-columnid="gridcolumn-1299"]')).last
        if not await row.is_visible(timeout=3000):
            print(" [FAIL] 找不到新增行")
            return False

    await page.evaluate("""() => {
        var grids = document.querySelectorAll('.x-grid-view');
        for (var g of grids) {
            if (g.scrollTo) g.scrollTo(0, g.scrollHeight);
            else if (g.scrollTop !== undefined) g.scrollTop = g.scrollHeight;
        }
    }""")
    await asyncio.sleep(0.5)

    # 填入顺序：日期 → 料号 → 数量 → 组织 → 接收地址 → 备注
    # 日期先填（键盘输入，tab=False 避免触发校验）
    await fill_cell_click_type(page, row, "gridcolumn-1306", date_str, tab=False)
    await asyncio.sleep(0.5)
    # 料号（无Tab）
    await fill_cell_click_type(page, row, "gridcolumn-1299", mat_code, tab=False)
    await asyncio.sleep(0.5)
    # 数量（去掉Tab，下一格由下个 fill_cell_click_type 直接点击进入）
    await fill_cell_click_type(page, row, "gridcolumn-1305", qty, tab=False)
    # 组织代码 M03
    await fill_cell_click_type(page, row, "gridcolumn-1307", "M03")
    await asyncio.sleep(0.5)
    # 接收地址
    await fill_cell_click_type(page, row, "gridcolumn-1310", "洗衣机三工厂")
    await asyncio.sleep(0.5)
    # 备注（Tab跳过或输入）
    if remarks:
        await page.keyboard.type(remarks, delay=30)
        await asyncio.sleep(0.3)
    else:
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.3)

    return True


async def _click_save(page, mat_code=""):
    """公用：点击保存按钮 → 检测弹窗 → 确定关闭，返回 (True/'') 或 (False/错误文本)"""
    for sel in ['#splitbutton-1164', 'span.x-btn-inner:has-text("保存")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                print(" [操作] 保存")
                await asyncio.sleep(0.5)
                break
        except Exception:
            continue

    # 捕获弹窗文本用于错误检测 AND 物料验证
    dialog_text = await _capture_save_dialog(page)

    if dialog_text:
        # 1) 错误关键词检测
        if any(kw in dialog_text for kw in ["失败", "错误", "非法", "Error", "error", "异常", "操作失败"]):
            print(f" [保存] 弹窗含错误信息，中止")
            await _close_save_dialog(page)
            return False, dialog_text.split(' |~| ')[0].strip()[:200]

        # 2) 物料验证：保存后检查该物料是否真的出现在单据明细中
        if mat_code and mat_code not in dialog_text:
            print(f" [FAIL] 物料 {mat_code} 未出现在保存结果单据中，可能未被系统接受")
            await _close_save_dialog(page)
            return False, f"物料 {mat_code} 保存后未出现在单据明细中（可能物料不存在或已被移除）"

        print(" [保存] 成功，物料已确认出现在单据中")
    else:
        print(f" [保存] 弹窗: (空/未检测到)")

    await _close_save_dialog(page)
    return True, ""


async def _capture_save_dialog(page):
    """捕获保存弹窗文本，返回合并文本或空字符串"""
    await asyncio.sleep(1)  # 等待弹窗稳定
    try:
        dialog_selectors = [
            '.layui-layer-content',
            '.x-message-box .x-window-text',
            '.x-window-body',
            '.x-window-bwrap',
            '[class*="msgbox"] .x-window-body',
        ]
        all_texts = []
        for sel in dialog_selectors:
            try:
                elements = page.locator(sel)
                count = await elements.count()
                for idx in range(count):
                    el = elements.nth(idx)
                    if await el.is_visible(timeout=300):
                        text = (await el.inner_text()).strip()
                        if text:
                            text = ' '.join(text.split())
                            all_texts.append(text)
            except Exception:
                continue
        if all_texts:
            joined = ' |~| '.join(all_texts)
            print(f" [保存] 弹窗: {joined[:300]}")
            return joined
    except Exception as e:
        print(f" [WARN] 弹窗检测异常: {e}")
    print(" [保存] 弹窗: (空/未检测到)")
    return ""


async def _close_save_dialog(page):
    """关闭保存结果弹窗"""
    for sel in ['.layui-layer-btn0', 'a.layui-layer-btn0',
                '.x-window:visible .x-btn-inner:has-text("确定")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                print(" [操作] 保存确认")
                await asyncio.sleep(0.5)
                return
        except Exception:
            continue


async def save_row_only(page, mat_code=""):
    """仅保存（无审核/启动）"""
    ok, err = await _click_save(page, mat_code)
    if not ok:
        return err
    print(" [OK] 保存完成")
    return True


async def save_and_audit_row(page, mat_code=""):
    """保存 → 确定 → 审核 → 启动 → 确定"""
    ok, err = await _click_save(page, mat_code)
    if not ok:
        return err

    for sel in ['#button-1168', 'span.x-btn-inner:has-text("审核")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                print(" [操作] 审核")
                await asyncio.sleep(0.8)
                break
        except Exception:
            continue

    for sel in ['#button-1962', 'span.x-btn-inner:has-text("启动")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=5000):
                await btn.click(force=True)
                print(" [操作] 启动")
                await asyncio.sleep(1)
                break
        except Exception:
            continue

    for sel in ['#button-1994', 'span.x-btn-inner:has-text("确定")',
                '.x-window:visible .x-btn-inner:has-text("确定")',
                '.layui-layer-btn0']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=5000):
                await btn.click()
                print(" [操作] 最终确定")
                await asyncio.sleep(1)
                break
        except Exception:
            continue

    print(" [OK] 保存审核完成")
    return True


# ============================================================
# 批量导入（所有物料一次导航，逐行新增填数据，统一保存审核）
# ============================================================

async def import_batch_items(page, items):
    """
    批量录入
    - 一次导航到导入页
    - 循环：点击新增 → 填6列 → 每行立即保存，末行保存+审核
    - 返回: (True, "") 或 (False, error_msg)
    """
    global _data_entry_started
    _data_entry_started = True

    print(f"\n  [批量导入] 共 {len(items)} 条，逐行新增填数据...")

    # 逐行新增 + 填数据（日期先填），每行保存，最后一行保存+审核
    for idx, item in enumerate(items, 1):
        is_last = (idx == len(items))
        print(f"\n  --- 第 {idx}/{len(items)} 行{' (最后一行)' if is_last else ''} ---")
        fill_ok = await import_single_item(page, item)
        if not fill_ok:
            error_msg = f"第 {idx} 行 ({item[0]}) 填数据失败"
            print(f" [FAIL] {error_msg}")
            return False, error_msg

        # 每填完一行立即保存
        ts(f"第 {idx} 行填写完成，保存...")
        if is_last:
            # 最后一行：保存+审核+启动
            save_result = await save_and_audit_row(page, item[0])
        else:
            # 非末行：仅保存
            save_result = await save_row_only(page, item[0])
        if save_result is not True:
            err = save_result if isinstance(save_result, str) else "保存失败（未知错误）"
            print(f" [FAIL] 第 {idx} 行保存失败: {err}")
            return False, f"第 {idx} 行 ({item[0]}) 保存失败: {err}"
        print(f" [OK] 第 {idx} 行保存{'审核' if is_last else ''}完成")
        await asyncio.sleep(1)

    ts(f"全部 {len(items)} 行处理完成")
    return True, ""


# ============================================================
# 回货计划发放 — 筛选 → 全选 → 发放
# ============================================================




async def release_huihuo(page, first_material):
    print(f"\n{'='*50}")
    print(f"回货计划发放 料号: {first_material}")
    print("=" * 50)

    # 筛选
    print(" [操作] 筛选...")
    clicked = False
    for s in ['#button-1190', 'a.x-btn:has-text("筛选")', 'span.x-btn-inner:has-text("筛选")']:
        try:
            fb = page.locator(s).first
            if await fb.is_visible(timeout=3000):
                await fb.click(force=True); clicked = True; break
        except Exception:
            continue
    if not clicked:
        print(" [FAIL] 筛选按钮"); return False
    await asyncio.sleep(1)

    for name in ["itemcode_start", "itemcode_end"]:
        try:
            inp = page.locator(f'input[name="{name}"]').first
            if await inp.is_visible(timeout=3000):
                await inp.click(click_count=3)
                await asyncio.sleep(0.2)
                await page.keyboard.press("Delete")
                await asyncio.sleep(0.2)
                await inp.fill(first_material)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Tab")
                await asyncio.sleep(0.3)
                print(f" [OK] {name} = {first_material}")
        except Exception as e:
            print(f" [WARN] {name}: {e}")

    for cb_name, cb_label in [("deliverinfore_released", "只显示未完全分配的数据")]:
        try:
            inp = page.locator(f'input[name="{cb_name}"]').first
            if await inp.is_visible(timeout=3000):
                if not await inp.is_checked():
                    await inp.check()
                    print(f" [OK] 勾选 {cb_label}")
            else:
                lbl = page.locator(f'label:has-text("{cb_label}")').first
                if await lbl.is_visible(timeout=2000):
                    await lbl.click()
                    print(f" [OK] 点击 {cb_label}")
        except Exception:
            pass
        await asyncio.sleep(0.3)

    # 新导入计划缺料=0，必须取消 filter_zero 否则全部被过滤
    for cb_name, cb_label in [("filter_zero", "滤掉缺料为0的数据")]:
        try:
            inp = page.locator(f'input[name="{cb_name}"]').first
            if await inp.is_visible(timeout=3000):
                if await inp.is_checked():
                    await inp.uncheck()
                    print(f" [OK] 取消 {cb_label}")
            else:
                lbl = page.locator(f'label:has-text("{cb_label}")').first
                if await lbl.is_visible(timeout=2000):
                    await lbl.click()
                    print(f" [OK] 切换 {cb_label}")
        except Exception:
            pass
        await asyncio.sleep(0.3)

    await asyncio.sleep(1)
    try:
        ok = page.locator(
            '.x-window:visible .x-btn-inner:has-text("确定"), '
            '.x-layer:visible .x-btn-inner:has-text("确定"), '
            'span.x-btn-inner:has-text("确定")'
        ).first
        if await ok.is_visible(timeout=5000):
            await ok.click(force=True)
            print(" [OK] 确定")
        else:
            print(" [FAIL] 无确定"); return False
    except Exception as e:
        print(f" [FAIL] 确定: {e}"); return False

    await wait_loadmask(page, "查询")

    await asyncio.sleep(1)
    try:
        chk = page.locator('.x-column-header-checkbox').first
        if await chk.is_visible(timeout=5000):
            await chk.click()
            print(" [OK] 全选")
        else:
            print(" [FAIL] 全选框"); return False
    except Exception as e:
        print(f" [FAIL] 全选: {e}"); return False
    await asyncio.sleep(1)

    for sel in ['#button-1403', 'span.x-btn-inner:has-text("发放")', 'a.x-btn:has-text("发放")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                print(" [OK] 发放")
                await asyncio.sleep(1)
                break
        except Exception:
            continue

    dialog_error = await detect_dialog_error(page, "发放")
    if dialog_error:
        print("\n [FAIL] 发放失败！")
        return dialog_error

    for sel in ['.layui-layer-btn0', 'a.layui-layer-btn0',
                '.layui-layer-btn .layui-layer-btn0',
                '.x-window:visible .x-btn-inner:has-text("确定")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                print(" [OK] 确认弹窗")
                break
        except Exception:
            continue

    await asyncio.sleep(1)
    print("\n [OK] 发放完成！")
    return True


# ============================================================
# 创建浏览器实例
# ============================================================

async def create_browser(playwright, headless=False):
    """创建Edge浏览器实例（默认可见模式，--headless 启用无头）"""
    browser = await playwright.chromium.launch(
        channel="msedge", headless=headless,
        args=["--disable-blink-features=AutomationControlled",
              "--no-sandbox", "--ignore-certificate-errors"],
    )
    context = await browser.new_context(
        ignore_https_errors=True,
        viewport={"width": 1280, "height": 800},
        locale="zh-CN", timezone_id="Asia/Shanghai",
    )
    page = await context.new_page()
    return browser, page


# ============================================================
# 主流程
# ============================================================

async def run_main(items, headless=False):
    """
    直通批量导入模式：登录 → 批量导入 → 逐条发放
    - 导入：一次导航，逐行新增填数据，统一保存审核
    - 发放：一次导航，逐条筛选发放，单条失败不中断
    """
    global _data_entry_started

    # 快速格式检查
    print("\n检查输入格式...")
    valid_items = []
    for idx, item in enumerate(items, 1):
        err = _check_item(item)
        if err:
            print(f" [ERR] 第{idx}行: {err}")
            continue
        mat = item[0].strip().upper()
        qty = str(int(item[1].strip()))
        date_str = item[2] if len(item) >= 3 and item[2] else ""
        remark = item[3].strip() if len(item) >= 4 and item[3] else ""
        valid_items.append((mat, qty, date_str, remark))

    if not valid_items:
        print("[FAIL] 无有效物料，拒绝执行")
        SUMMARY["status"] = "failure (validation)"
        return False

    skipped = len(items) - len(valid_items)
    if skipped:
        print(f" [WARN] {skipped} 条格式异常已跳过，处理 {len(valid_items)} 条")

    items = valid_items

    # 浏览器启动 & 登录
    try:
        p = await async_playwright().start()
    except Exception as e:
        print(f" [FAIL] 启动 Playwright: {e}")
        SUMMARY["status"] = "failure (playwright)"
        return False

    try:
        try:
            browser, page = await create_browser(p, headless)
        except Exception as e:
            print(f" [FAIL] 启动浏览器: {e}")
            await p.stop()
            SUMMARY["status"] = "failure (browser)"
            return False

        ok = await login_scm(page, USERNAME, PASSWORD)
        if not ok:
            print("[FAIL] 登录失败")
            try: await browser.close()
            except: pass
            await p.stop()
            SUMMARY["status"] = "failure (login)"
            return False

        if not await check_session_alive(page):
            print("[FAIL] 会话检查失败")
            try: await browser.close()
            except: pass
            await p.stop()
            SUMMARY["status"] = "failure (session)"
            return False

        # 批量导入
        ts("批量导入（一次导航，逐行新增填数据，统一保存审核）...")
        ok = await nav_to(page, "供应链管理", "配送管理", "回货计划导入")
        if not ok:
            print("[FAIL] 导入页导航失败")
            try: await browser.close()
            except: pass
            await p.stop()
            SUMMARY["status"] = "failure (navigation)"
            return False
        await asyncio.sleep(1)

        import_ok, import_error = await import_batch_items(page, items)
        ts("关闭导入页签")
        await close_tab(page)

        if not import_ok:
            for item in items:
                _add_item_summary(item[0], item[1], item[3], False, False, import_error)
            SUMMARY["status"] = "failure (batch import)"
            _print_summary()
            try: await browser.close()
            except: pass
            await p.stop()
            return False

        # 逐条发放（容错模式）
        ts("逐条发放（一次导航，逐条筛选发放，失败不中断）...")
        if not await check_session_alive(page):
            print("[FAIL] 发放前会话检查失败")
            for item in items:
                _add_item_summary(item[0], item[1], item[3], True, False, "会话过期")
            SUMMARY["status"] = "failure (session)"
            _print_summary()
            try: await browser.close()
            except: pass
            await p.stop()
            return False

        nav_ok = await nav_to(page, "供应链管理", "配送管理", "回货计划发放")
        if not nav_ok:
            print("[FAIL] 发放页导航失败")
            for item in items:
                _add_item_summary(item[0], item[1], item[3], True, False, "发放导航失败")
            SUMMARY["status"] = "failure (navigation)"
            _print_summary()
            try: await browser.close()
            except: pass
            await p.stop()
            return False

        success_count = 0
        fail_count = 0
        for idx, item in enumerate(items, 1):
            mat_code = item[0]
            print(f"\n  --- 发放第 {idx}/{len(items)} 条: {mat_code} ---")
            release_result = await release_huihuo(page, mat_code)
            if release_result is True:
                _add_item_summary(mat_code, item[1], item[3], True, True, "")
                success_count += 1
                print(f" [OK] {mat_code} 发放成功 ({success_count}成功/{fail_count}失败)")
            else:
                error_msg = release_result if isinstance(release_result, str) else "发放返回异常"
                _add_item_summary(mat_code, item[1], item[3], True, False, error_msg)
                fail_count += 1
                print(f" [FAIL] {mat_code} 发放失败: {error_msg} ({success_count}成功/{fail_count}失败)")

        ts("关闭发放页签")
        await close_tab(page)

        SUMMARY["status"] = "partial_success" if fail_count > 0 and success_count > 0 else (
            "success" if fail_count == 0 else "failure (all release failed)")
        _print_summary()

        ts(f"处理完成: {success_count} 成功, {fail_count} 失败")
        ts("关闭浏览器")
        try: await browser.close()
        except: pass
        await p.stop()
        return fail_count == 0

    except Exception as e:
        print(f"\n[ERR] 发生异常: {e}")
        import traceback
        traceback.print_exc()
        try:
            if 'browser' in dir() and browser:
                if not page.is_closed():
                    await browser.close()
        except Exception:
            pass
        await p.stop()
        SUMMARY["status"] = "failure (exception)"
        _print_summary()
        if _data_entry_started:
            print("\n[FAIL] 已在填写数据过程中发生异常，中止运行")
            print(" 原因：数据可能已部分写入，请手动检查 SCM 系统")
        return False


# ============================================================
# 入口
# ============================================================

async def main():
    global _data_entry_started
    _data_entry_started = False

    ts("=" * 50)
    ts("SCM 回货计划导入 & 发放 v2.2 (直通批量导入)")
    ts("=" * 50)

    import argparse
    parser = argparse.ArgumentParser(description="回货计划导入发放")
    parser.add_argument("--data", help="料号数量数据，格式: '料号1 数量1 备注1, 料号2 数量2'")
    parser.add_argument("--headless", action="store_true", help="无头模式运行（默认可见模式）")

    args = parser.parse_args()

    items = []

    def parse_line(parts):
        cleaned = [p.replace(',', '').replace('，', '') for p in parts if p]
        if len(cleaned) >= 4:
            return (cleaned[0], cleaned[1], cleaned[2], cleaned[3])
        elif len(cleaned) >= 3:
            p2 = cleaned[2]
            m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', p2)
            if m:
                norm_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                return (cleaned[0], cleaned[1], norm_date, "")
            else:
                return (cleaned[0], cleaned[1], "", p2)
        elif len(cleaned) >= 2:
            return (cleaned[0], cleaned[1], "", "")
        return None

    if args.data:
        raw = args.data
        groups = re.split(r'[,，]', raw)
        for g in groups:
            parts = re.split(r'[\t\s]+', g.strip())
            item = parse_line(parts)
            if item:
                items.append(item)
    else:
        print("\n请输入数据（料号 数量 [备注]），每行一条，空行结束:")
        while True:
            try:
                line = input().strip()
                if not line:
                    break
                parts = re.split(r'[\t,，\s]+', line)
                item = parse_line(parts)
                if item:
                    items.append(item)
            except (EOFError, KeyboardInterrupt):
                break

    if not items:
        print("[ERR] 未输入有效数据")
        return

    print(f"\n解析到 {len(items)} 条:")
    for item in items:
        m, q = item[0], item[1]
        d = item[2] if len(item) >= 3 and item[2] else ""
        r = item[3] if len(item) >= 4 and item[3] else ""
        info = f"  {m:30s} → {q:>8s}"
        if d:
            info += f"  日期: {d}"
        if r:
            info += f"  备注: {r}"
        print(info)

    if not args.data:
        input("\n确认无误后按 Enter 开始...")

    success = await run_main(items, headless=args.headless)

    if not success:
        print("\n[FAIL] 回货流程完成（有失败项）")
        sys.exit(1)
    else:
        print("\n[OK] 回货流程全部成功")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
