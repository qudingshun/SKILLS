"""
回货计划导入 & 发放工具（OpenClaw 技能版）

用法:
  python huihuo_scm.py --data "70C11099 2"                    # 单行
  python huihuo_scm.py --data "70C11099 2 售后配件"           # 单行+备注
  python huihuo_scm.py --data "70C11099 2, ABC 3 紧急补货"   # 多行
"""
import asyncio
import os
import re
import sys
import calendar
from datetime import date
from playwright.async_api import async_playwright

# ── WHP-scm-suite 共享核心引导 ──────────────────────────────
SUITE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(SUITE_DIR, "scripts"))
CONFIG_PATH = os.path.join(SUITE_DIR, "runtime_config.json")

from wh_core.secure_config import ConfigManager, SecurePasswordManager

SCM_URL = "https://scm.whirlpool-china.com:7580/websrm/"

# 从中央配置读取凭据（密码优先取 AES 加密库，回退配置文件）
_cfg = ConfigManager(CONFIG_PATH)
_sm = SecurePasswordManager(_cfg)
USERNAME = _cfg.get_sc_config("username", "hsa697")
PASSWORD = _sm.load_password("scm") or _cfg.get_sc_config("password", "")
MAX_LOGIN_RETRIES = 3

# ============================================================
# 全局标志：记录是否已开始填写数据（用于决定异常时是否重试）
# ============================================================
_data_entry_started = False

# ============================================================
# 日志工具 & 摘要追踪
# ============================================================
import datetime as _dt
_START_TIME = _dt.datetime.now()

def ts(msg=""):
    """带时间戳的日志输出"""
    t = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"[{t}] {msg}")

# 执行摘要，用于脚本末尾统一输出
SUMMARY = {
    "started": _START_TIME.strftime("%Y-%m-%d %H:%M:%S"),
    "ended": None,
    "duration_s": None,
    "status": "unknown",
    "items": [],
}

def _add_item_summary(mat, qty, remark, import_ok, release_ok):
    SUMMARY["items"].append({
        "material": mat,
        "qty": qty,
        "remark": remark,
        "import": "OK" if import_ok else "FAIL",
        "release": "OK" if release_ok else ("SKIP" if import_ok else "-"),
    })

def _print_summary():
    now = _dt.datetime.now()
    SUMMARY["ended"] = now.strftime("%Y-%m-%d %H:%M:%S")
    SUMMARY["duration_s"] = round((now - _START_TIME).total_seconds(), 1)
    print()
    print("=" * 50)
    print("=== SUMMARY ===")
    print(f"  status:    {SUMMARY['status']}")
    print(f"  started:   {SUMMARY['started']}")
    print(f"  ended:     {SUMMARY['ended']}")
    print(f"  duration:  {SUMMARY['duration_s']}s")
    print(f"  items:     {len(SUMMARY['items'])}")
    for i, item in enumerate(SUMMARY["items"], 1):
        print(f"    [{i}] {item['material']} x{item['qty']}" + (f" ({item['remark']})" if item["remark"] else ""))
        print(f"         import={item['import']}  release={item['release']}")
    print("=" * 50)

# ============================================================
# 登录函数
# ============================================================

async def is_logged_in(page) -> bool:
    try:
        has_login = await page.evaluate("""() => {
            var u = document.querySelector('#username');
            var p = document.querySelector('input[type="password"]');
            var k = document.querySelector('#kaptcha');
            if (p || k) return true;
            if (u && u.offsetParent !== null) return true;
            return false;
        }""")
        return not has_login
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
        import base64
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
    print(" [登录] 打开SCM...")
    await page.goto(SCM_URL, timeout=60000)
    await asyncio.sleep(3)
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    await asyncio.sleep(2)

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
                await asyncio.sleep(1)
            except Exception:
                pass
        captcha = await recognize_captcha(page)
        if captcha:
            print(f" [登录] OCR: {captcha}")
            break

    if not captcha:
        print("\n OCR 3次失败，请在浏览器中手动输入验证码后点击登录按钮")
        print(" 脚本将等待60秒...")
        for _ in range(60):
            await asyncio.sleep(1)
            if await is_logged_in(page):
                print(" [OK] 登录成功！")
                return True
        return False

    if captcha:
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

    await asyncio.sleep(5)
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    await asyncio.sleep(3)

    ok = await is_logged_in(page)
    print(" [OK] 登录成功！" if ok else " [FAIL] 登录失败")
    return ok


# ============================================================
# 导航 & 工具
# ============================================================

async def nav_to(page, accordion_text, menu_text, button_text):
    await page.goto(SCM_URL, timeout=30000)
    await asyncio.sleep(3)
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        pass
    await asyncio.sleep(2)

    try:
        loc = page.locator(f"text={accordion_text}").first
        if await loc.is_visible(timeout=5000):
            await loc.click()
            await asyncio.sleep(1.5)
    except Exception:
        pass

    try:
        loc = page.locator(f"text={menu_text}").first
        if await loc.is_visible(timeout=5000):
            await loc.click()
            await asyncio.sleep(1.5)
    except Exception:
        print(f" [FAIL] 未找到: {menu_text}")
        return False

    try:
        popup = page.locator(".crisp_menu_list")
        await popup.wait_for(state="visible", timeout=8000)
        btn = page.locator(f'.crisp_menu_list button:has-text("{button_text}")').first
        await btn.wait_for(state="visible", timeout=5000)
        await btn.click()
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await asyncio.sleep(2)
        return True
    except Exception as e:
        print(f" [FAIL] {button_text}: {e}")
        return False


async def close_tab(page):
    await asyncio.sleep(1)
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
            await asyncio.sleep(2)
            return True
        except Exception:
            continue
    return False


async def wait_loadmask(page, label="操作"):
    for i in range(120):
        await asyncio.sleep(1)
        loading = await page.evaluate("""() => {
            var m = document.querySelectorAll('[id^="loadmask-"]');
            for (var x of m) {
                if (x.classList.contains('x-mask') && x.style.display !== 'none') return true;
            }
            return false;
        }""")
        if not loading and i >= 3:
            print(f" [OK] {label} ~{i+1}s")
            return
    print(f" [WARN] {label} 超时")


# ============================================================
# 回货计划导入 — 新增行填数据
# ============================================================

async def fill_cell_click_type(page, row_locator, column_id, text, tab=True):
    """点击单元格 → 三击全选 → type输入（支持中文）"""
    try:
        cell = row_locator.locator(f'td[data-columnid="{column_id}"] .x-grid-cell-inner')
        if not await cell.is_visible(timeout=3000):
            return False

        await cell.click(force=True)
        await asyncio.sleep(0.5)
        await cell.click(click_count=3, force=True)
        await asyncio.sleep(0.3)
        await page.keyboard.press("Delete")
        await asyncio.sleep(0.2)
        await page.keyboard.type(text, delay=30)
        await asyncio.sleep(0.3)
        if tab:
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.5)
        return True
    except Exception as e:
        print(f" [WARN] {column_id}: {e}")
        try:
            await asyncio.sleep(0.3)
            await page.keyboard.press("Delete")
            await asyncio.sleep(0.2)
            await page.keyboard.type(text, delay=30)
            await asyncio.sleep(0.3)
            if tab:
                await page.keyboard.press("Tab")
                await asyncio.sleep(0.5)
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
        await asyncio.sleep(2)

        set_ok = await page.evaluate(f"""() => {{
            try {{
                var ed = document.querySelector('.x-grid-editor');
                if (!ed) return false;
                var inp = ed.querySelector('input');
                if (!inp) return false;
                var proto = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
                if (proto && proto.set) {{
                    proto.set.call(inp, '{date_text}');
                }} else {{
                    inp.value = '{date_text}';
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
        await asyncio.sleep(1.5)

        trigger = page.locator('.x-grid-editor .x-form-search-trigger, .x-grid-editor .x-trigger-index-0').first
        if await trigger.is_visible(timeout=3000):
            await trigger.click()
            await asyncio.sleep(3)
        else:
            trigger = page.locator('.x-form-search-trigger:visible').first
            if await trigger.is_visible(timeout=5000):
                await trigger.click()
                await asyncio.sleep(3)
            else:
                await page.keyboard.press("Alt+ArrowDown")
                await asyncio.sleep(2)

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
                    await asyncio.sleep(3)
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
                    await asyncio.sleep(2)
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
    """导入单行物料：新增→填6列→保存审核"""
    global _data_entry_started
    _data_entry_started = True  # 开始填写数据，之后异常不再重试

    mat_code, qty = item[0], item[1]
    remarks = item[2] if len(item) >= 3 and item[2].strip() else ""

    today = date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    date_str = f"{today.year}-{today.month:02d}-{last_day:02d}"
    print(f"  料号: {mat_code}  qty={qty}" + (f"  备注: {remarks}" if remarks else ""))
    print(f"  日期: {date_str}  组织: M03  工厂: 洗衣机三工厂")

    # 点击新增
    try:
        btn = page.locator('#button-1326')
        if await btn.is_visible(timeout=5000):
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

    row = page.locator('.x-grid-row:last-child')

    await page.evaluate("""() => {
        var grids = document.querySelectorAll('.x-grid-view');
        for (var g of grids) {
            if (g.scrollTo) g.scrollTo(0, g.scrollHeight);
            else if (g.scrollTop !== undefined) g.scrollTop = g.scrollHeight;
        }
    }""")
    await asyncio.sleep(0.5)

    # 1. 料号
    await fill_cell_click_type(page, row, "gridcolumn-1299", mat_code)
    await asyncio.sleep(0.5)
    # 2. 数量
    await fill_cell_click_type(page, row, "gridcolumn-1305", qty)
    await asyncio.sleep(0.5)
    # 3. 组织代码 M03
    await fill_cell_click_type(page, row, "gridcolumn-1307", "M03")
    await asyncio.sleep(0.5)
    # 4. 接收地址
    await fill_cell_click_type(page, row, "gridcolumn-1310", "洗衣机三工厂")
    await asyncio.sleep(0.5)
    # 5. 备注
    if remarks:
        await page.keyboard.type(remarks, delay=30)
        await asyncio.sleep(0.3)
    else:
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.3)
    # 6. 日期
    await fill_cell_click_type(page, row, "gridcolumn-1306", date_str, tab=False)
    await asyncio.sleep(0.5)

    # 验证
    columns_to_check = [
        ("gridcolumn-1299", "料号"),
        ("gridcolumn-1305", "数量"),
        ("gridcolumn-1307", "组织"),
        ("gridcolumn-1310", "接收地址"),
        ("gridcolumn-1312", "备注"),
        ("gridcolumn-1306", "日期"),
    ]
    all_filled = True
    for col_id, col_label in columns_to_check:
        if col_id == "gridcolumn-1312" and not remarks:
            continue
        try:
            text = await row.locator(f'td[data-columnid="{col_id}"] .x-grid-cell-inner').inner_text(timeout=2000)
            if not text.strip():
                print(f" [补填] {col_label} 为空...")
                if col_id == "gridcolumn-1306":
                    await fill_cell_click_type(page, row, col_id, date_str)
                elif col_id == "gridcolumn-1310":
                    await fill_cell_click_type(page, row, col_id, "洗衣机三工厂")
                elif col_id == "gridcolumn-1307":
                    await fill_cell_click_type(page, row, col_id, "M03")
                elif col_id == "gridcolumn-1312":
                    await fill_cell_click_type(page, row, col_id, remarks, tab=False)
                else:
                    val = mat_code if col_id == "gridcolumn-1299" else (qty if col_id == "gridcolumn-1305" else "")
                    if val:
                        await fill_cell_click_type(page, row, col_id, val)
                await asyncio.sleep(0.3)
                text2 = await row.locator(f'td[data-columnid="{col_id}"] .x-grid-cell-inner').inner_text(timeout=2000)
                if text2.strip():
                    print(f" [OK] 已补填: {text2.strip()}")
                else:
                    print(f" [WARN] {col_label} 补填后仍为空")
                    all_filled = False
        except Exception:
            print(f" [WARN] {col_label} 验证异常")
            all_filled = False

    if not all_filled:
        print(" [WARN] 部分列未填，仍尝试保存...")

    ts("填写完成，保存并审核...")
    await save_and_audit_row(page)
    ts("保存+审核完成")
    return True


async def save_and_audit_row(page):
    """保存 → 确定 → 审核 → 启动 → 确定"""
    for sel in ['#splitbutton-1164', 'span.x-btn-inner:has-text("保存")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                print(" [操作] 保存")
                await asyncio.sleep(2)
                break
        except Exception:
            continue

    for sel in ['.layui-layer-btn0', 'a.layui-layer-btn0',
                '.x-window:visible .x-btn-inner:has-text("确定")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=5000):
                await btn.click()
                print(" [操作] 保存确认")
                await asyncio.sleep(2)
                break
        except Exception:
            continue

    for sel in ['#button-1168', 'span.x-btn-inner:has-text("审核")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                print(" [操作] 审核")
                await asyncio.sleep(3)
                break
        except Exception:
            continue

    for sel in ['#button-1962', 'span.x-btn-inner:has-text("启动")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=5000):
                await btn.click(force=True)
                print(" [操作] 启动")
                await asyncio.sleep(2)
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
                await asyncio.sleep(2)
                break
        except Exception:
            continue

    print(" [OK] 导入完成")


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
        print(" [FAIL] 筛选按钮"); return
    await asyncio.sleep(2)

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

    for cb_name, cb_label in [("deliverinfore_released", "只显示未完全分配的数据"),
                                ("filter_zero", "滤掉缺料为0的数据")]:
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
            print(" [FAIL] 无确定"); return
    except Exception as e:
        print(f" [FAIL] 确定: {e}"); return

    await wait_loadmask(page, "查询")

    await asyncio.sleep(1)
    try:
        chk = page.locator('.x-column-header-checkbox').first
        if await chk.is_visible(timeout=5000):
            await chk.click()
            print(" [OK] 全选")
        else:
            print(" [FAIL] 全选框"); return
    except Exception as e:
        print(f" [FAIL] 全选: {e}"); return
    await asyncio.sleep(1)

    for sel in ['#button-1403', 'span.x-btn-inner:has-text("发放")', 'a.x-btn:has-text("发放")']:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=3000):
                await btn.click(force=True)
                print(" [OK] 发放")
                await asyncio.sleep(2)
                break
        except Exception:
            continue

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


# ============================================================
# 创建浏览器实例
# ============================================================

async def create_browser(playwright):
    """创建Edge浏览器实例"""
    browser = await playwright.chromium.launch(
        channel="msedge", headless=True,
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
# 主流程（带重试）
# ============================================================

async def run_main(items):
    """主执行流程，支持登录重试"""
    global _data_entry_started

    for attempt in range(1, MAX_LOGIN_RETRIES + 1):
        if attempt > 1:
            print(f"\n{'='*50}")
            print(f"第 {attempt} 次尝试登录...")
            print("=" * 50)

        p = await async_playwright().start()

        try:
            browser, page = await create_browser(p)
        except Exception as e:
            print(f" [FAIL] 启动浏览器: {e}")
            await p.stop()
            if attempt < MAX_LOGIN_RETRIES:
                print(" 浏览器启动失败，等待3秒后重试...")
                await asyncio.sleep(3)
                continue
            else:
                print(f"\n[FAIL] 连续 {MAX_LOGIN_RETRIES} 次启动浏览器失败，中止运行")
                return False

        try:
            ok = await login_scm(page, USERNAME, PASSWORD)
            if not ok:
                print(f"\n[FAIL] 第 {attempt} 次登录失败")
                try:
                    await browser.close()
                except Exception:
                    pass
                await p.stop()

                if attempt < MAX_LOGIN_RETRIES:
                    print(" 关闭浏览器，等待3秒后重试...\n")
                    await asyncio.sleep(3)
                    continue
                else:
                    print(f"\n[FAIL] 连续 {MAX_LOGIN_RETRIES} 次登录失败，中止运行")
                    print(" 可能原因：验证码识别持续失败、网络异常、账号密码问题")
                    return False

            # 登录成功，执行主流程
            for idx, item in enumerate(items, 1):
                mat_code = item[0]
                print(f"\n{'='*50}")
                ts(f"第 {idx}/{len(items)} 行：{mat_code}")
                print("=" * 50)

                # === 回货计划导入 ===
                ts("回货计划导入 ---")
                print()
                ok = await nav_to(page, "供应链管理", "配送管理", "回货计划导入")
                if not ok:
                    print("[FAIL] 导航失败，跳过此行")
                    continue
                print(" [等待] 页面加载稳定...")
                await asyncio.sleep(5)

                import_ok = await import_single_item(page, item)

                ts("关闭导入页签")
                await close_tab(page)

                # === 回货计划发放 ===
                release_ok = False
                ts("回货计划发放 ---")
                nav_ok = await nav_to(page, "供应链管理", "配送管理", "回货计划发放")
                if not nav_ok:
                    print("[FAIL] 导航失败，跳过此行发放")
                else:
                    await release_huihuo(page, mat_code)
                    release_ok = True
                    ts("关闭发放页签")
                    await close_tab(page)

                _add_item_summary(mat_code, item[1], item[2] if len(item) >= 3 and item[2].strip() else "", import_ok, release_ok)
                print(f"\n [OK] 第 {idx} 行完成！")

            SUMMARY["status"] = "success"
            _print_summary()
            ts("全部处理完成，关闭浏览器")
            try:
                await browser.close()
            except Exception:
                pass
            await p.stop()
            return True

        except Exception as e:
            print(f"\n[ERR] 发生异常: {e}")
            import traceback
            traceback.print_exc()

            try:
                if not page.is_closed():
                    await browser.close()
            except Exception:
                pass
            await p.stop()

            SUMMARY["status"] = "failure (data entry)" if _data_entry_started else "failure (login)"
            _print_summary()
            if _data_entry_started:
                print("\n[FAIL] 已在填写数据过程中发生异常，不重试，中止运行")
                print(" 原因：数据可能已部分写入，重新执行可能导致重复或数据不一致")
                return False

            if attempt < MAX_LOGIN_RETRIES:
                print(f" 关闭浏览器，等待5秒后重试（{attempt}/{MAX_LOGIN_RETRIES}）...\n")
                await asyncio.sleep(5)
                continue
            else:
                SUMMARY["status"] = "failure (max retries)"
                _print_summary()
                print(f"\n[FAIL] 连续 {MAX_LOGIN_RETRIES} 次失败，中止运行")
                return False

    SUMMARY["status"] = "failure (unexpected exit)"
    _print_summary()
    return False


# ============================================================
# 入口
# ============================================================

async def main():
    global _data_entry_started
    _data_entry_started = False

    ts("=" * 50)
    ts("SCM 回货计划导入 & 发放")
    ts("=" * 50)

    import argparse
    parser = argparse.ArgumentParser(description="回货计划导入发放")
    parser.add_argument("--data", help="料号数量数据，格式: '料号1 数量1 备注1, 料号2 数量2'")
    parser.add_argument("--list", action="store_true", help="列出可用任务")
    args = parser.parse_args()

    if args.list:
        print("可用任务: run (执行导入+发放)")
        return

    items = []

    def parse_line(parts):
        cleaned = [p.replace(',', '').replace('，', '') for p in parts if p]
        if len(cleaned) >= 3:
            return (cleaned[0], cleaned[1], cleaned[2])
        elif len(cleaned) >= 2:
            return (cleaned[0], cleaned[1], "")
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
        r = item[2] if len(item) >= 3 and item[2] else ""
        print(f"  {m:30s} → {q:>8s}" + (f"  备注: {r}" if r else ""))

    if not args.data:
        input("\n确认无误后按 Enter 开始...")

    success = await run_main(items)

    if not success:
        print("\n[FAIL] 回货流程失败")
        sys.exit(1)
    else:
        print("\n[OK] 回货流程执行完毕")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
