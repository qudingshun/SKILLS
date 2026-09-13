#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WHP-system-data-query —— 查询并展示系统数据

功能：
  1. 帆软(库存报表)：根据 料号(必填) + 可选 组织/工厂 + 可选 货位，查询 库存现有量。
  2. SCM 系统：针对一个 料号，查询并展示 5 类数据：
       - 回货计划发放（可下发送货通知 = 是 / 否 两个数量）
       - 送货通知单的未制单数量
       - 送货单的 未接收已报检 / 未接受未报检 数量
       - 采购订单未结量物料汇总的 剩余可发布送货通知总量
       - 请购单中 行状态=下达 的请购单总数量

用法示例：
  py scripts/system_data_query.py --material 123456
  py scripts/system_data_query.py --material 123456 --org M03
  py scripts/system_data_query.py --material 123456 --bin A01-01
  py scripts/system_data_query.py --material 123456 --module scm
  py scripts/system_data_query.py --material 123456 --module fanruan
"""
import sys
import os
import json
import asyncio
import argparse
import base64

# ── WHP-scm-suite 共享核心引导 ──────────────────────────────
# 本脚本位于 <suite>/scripts/<module>/，套件根为上级两级目录
SUITE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(SUITE_DIR, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SUITE_DIR, "runtime_config.json")

from wh_core.whirlpool_common import (
    create_browser, load_storage_state, save_storage_state,
    safe_print, check_dependencies, is_headless,
)
from wh_core.secure_config import ConfigManager, SecurePasswordManager

# ── 常量 ──────────────────────────────────────────────────────
BASE = os.path.dirname(os.path.abspath(__file__))
STORAGE_FILE_SCM = os.path.join(BASE, "scm_storage_state.json")
STORAGE_FILE_FR = os.path.join(BASE, "fanruan_storage_state.json")

SCM_URL = "https://scm.whirlpool-china.com:7580/websrm/index.jsp"
FANRUAN_BASE_URL = "https://rpt.whirlpool-china.com:7027/decision"
STOCK_REPORT_URL = FANRUAN_BASE_URL + "/v10/entry/access/old-platform-reportlet-entry-573?width=2320&height=1376"

# SCM 菜单导航 (accordion, menu, button)
NAV_CONFIG = [
    ("供应链执行", "采购执行", "送货通知查询"),
    ("供应链执行", "采购执行", "送货单查询"),
    ("供应链执行", "采购执行", "采购订单未结量物料汇总查询"),
    ("供应链执行", "采购执行", "回货计划/发放"),
    ("供应链执行", "采购计划", "请购单查询"),
]

# 帆软库存报表的料号/货位参数控件候选名
FR_ITEM_WIDGETS = ["P_ITEMID", "ITEMID", "P_ITEM_ID", "ITEM_ID", "item_code", "P_ITEMCODE"]
FR_BIN_WIDGETS = ["P_BIN", "BIN", "P_LOCATION", "LOCATION", "P_STORAGE",
                  "STORAGE_LOCATION", "P_BIN_CODE", "货位", "P_BINLOC"]

# SCM 料号过滤字段候选名
SCM_MATERIAL_FIELDS = ["item_code", "sap_item_code", "material_code", "mat_code",
                       "product_code", "item_no", "material_no", "sap_material_code",
                       "item_bh", "material_bh"]

# ── 网格提取 JS（复用 WHP-whirlpool-download 的 EXTRACT_GRID） ──────────
EXTRACT_GRID = """async () => {
    try {
        // 优先 ExtJS 网格（SCM）
        if (typeof Ext !== 'undefined') {
            var gvs = Ext.ComponentQuery.query('gridview');
            for (var g of gvs) {
                try {
                    if (!g.getEl || g.getEl().isVisible(false) === false) continue;
                    var ds = g.getStore ? g.getStore() : null;
                    if (!ds || ds.getCount() === 0) continue;
                    var cols = [];
                    var hds = g.panel.headerCt.getGridColumns ? g.panel.headerCt.getGridColumns() : (g.panel.headerCt.items.items || []);
                    for (var c of hds) {
                        if (c.hidden) continue;
                        if (c.dataIndex === undefined && c.text === undefined) continue;
                        cols.push({ key: c.dataIndex || c.text, header: c.text || c.dataIndex });
                    }
                    var data = [];
                    ds.each(function(rec) {
                        var row = {};
                        for (var c of cols) row[c.key] = rec.get(c.key);
                        data.push(row);
                    });
                    if (data.length) return { rc: data.length, cols: cols, data: data };
                } catch (e) {}
            }
        }
        // DOM 兜底（帆软 / 其他）
        var tbl = document.querySelector('.x-grid-view tbody') || document.querySelector('.x-grid3-body')
               || document.querySelector('table.x-grid-table') || document.querySelector('.x-grid-table');
        if (tbl) {
            var trs = tbl.querySelectorAll('tr');
            var cols = [], data = [];
            trs.forEach(function(tr) {
                var tds = tr.querySelectorAll('td');
                if (!cols.length) {
                    tds.forEach(function(td, i) { cols.push({ key: 'c'+i, header: (td.innerText||'').trim() }); });
                } else {
                    var row = {};
                    tds.forEach(function(td, i) { row['c'+i] = (td.innerText||'').trim(); });
                    data.push(row);
                }
            });
            if (data.length) return { rc: data.length, cols: cols, data: data };
        }
        // 更宽泛兜底
        var anyTbl = document.querySelector('table');
        if (anyTbl) {
            var trs2 = anyTbl.querySelectorAll('tr');
            var cols2 = [], data2 = [];
            trs2.forEach(function(tr) {
                var tds = tr.querySelectorAll('td,th');
                var row = {};
                tds.forEach(function(td, i) {
                    var txt = (td.innerText||'').trim();
                    row['c'+i] = txt;
                    if (!cols2.length && td.tagName === 'TH') cols2.push({key:'c'+i, header: txt});
                });
                if (Object.keys(row).length) data2.push(row);
            });
            if (cols2.length) return { rc: data2.length, cols: cols2, data: data2 };
            if (data2.length) return { rc: data2.length, cols: cols2, data: data2 };
        }
        return { rc: 0, cols: [], data: [] };
    } catch (e) { return { rc: -1, error: e.message }; }
}"""


# ── 通用工具 ──────────────────────────────────────────────
def to_display_rows(raw):
    """把 {cols:[{key,header}], data:[{...}]} 转成 以表头为中文键 的行列表"""
    cols = raw.get("cols", []) or []
    data = raw.get("data", []) or []
    rows = []
    for d in data:
        row = {}
        for c in cols:
            row[c.get("header")] = d.get(c.get("key"))
        rows.append(row)
    return rows


def find_col(headers, *keywords):
    """返回第一个匹配任一关键字的表头（子串，忽略大小写）"""
    for h in headers:
        for kw in keywords:
            if kw and kw.lower() in str(h).lower():
                return h
    return None


def _to_float(v):
    try:
        return float(str(v).replace(",", "").replace("，", "").strip())
    except Exception:
        return None


def sum_col(rows, header):
    total, cnt = 0.0, 0
    for r in rows:
        f = _to_float(r.get(header))
        if f is not None:
            total += f
            cnt += 1
    return total, cnt


def count_by_value(rows, header, value):
    return sum(1 for r in rows if str(r.get(header, "")).strip() == str(value).strip())


def print_table(headers, rows, max_rows=50):
    cols = list(headers)
    widths = [len(str(c)) for c in cols]
    for r in rows[:max_rows]:
        for i in range(len(cols)):
            v = str(r[i]) if i < len(r) else ""
            widths[i] = max(widths[i], len(v))
    sep = "-" * (sum(widths) + 3 * len(cols))

    def fmt(row):
        return " | ".join(str(row[i] if i < len(row) else "").ljust(widths[i]) for i in range(len(cols)))

    safe_print(sep)
    safe_print(fmt(cols))
    safe_print(sep)
    for r in rows[:max_rows]:
        safe_print(fmt(r))
    if len(rows) > max_rows:
        safe_print(f"  ... 共 {len(rows)} 行，仅显示前 {max_rows} 行")


# ── SCM 查询 ──────────────────────────────────────────────
class QuerySCM:
    def __init__(self, config_manager, secure_manager):
        self.config_manager = config_manager
        self.secure_manager = secure_manager

    # ── 登录 ──
    async def is_logged_in(self, page) -> bool:
        try:
            cur = page.url
            if "#appcentral" in cur or "menu" in cur or "main" in cur:
                return True
            r = await page.evaluate("""() => {
                var u = document.querySelector('#username');
                if (u && u.offsetParent !== null) return false;
                u = document.querySelector('#password');
                if (u && u.offsetParent !== null) return false;
                u = document.querySelector('#kaptcha');
                if (u && u.offsetParent !== null) return false;
                var t = document.title || '';
                var b = document.body ? document.body.innerText || '' : '';
                if (t.includes('SCM') || t.includes('供应链') || b.includes('注销') || b.includes('退出') || b.includes('首页')) return true;
                var url = location.href;
                if (url.includes('#appcentral') || url.includes('/main') || url.includes('/menu')) return true;
                return false;
            }""")
            return r
        except Exception:
            return False

    async def _recognize_captcha(self, page):
        try:
            b64 = await page.evaluate("""async () => {
                var img = document.querySelector('#changeCode');
                if (!img) return null;
                try {
                    var r = await fetch(img.src + '?' + Date.now(), {cache: 'no-cache'});
                    var b = await r.blob();
                    return await new Promise(function(resolve) {
                        var reader = new FileReader();
                        reader.onloadend = function() { resolve(reader.result); };
                        reader.readAsDataURL(b);
                    });
                } catch(e) { return null; }
            }""")
            if not b64 or "," not in b64:
                safe_print("  [OCR] 无法获取验证码图片")
                return None
            img_bytes = base64.b64decode(b64.split(",")[1])
            try:
                import ddddocr
                ocr = ddddocr.DdddOcr(show_ad=False)
                result = ocr.classification(img_bytes)
                result = result.strip() if result else ""
                if result and len(result) == 4 and result.isascii() and result.isalnum():
                    safe_print(f"  [OCR] 识别结果：{result}")
                    return result
                safe_print(f"  [OCR] 识别结果无效: '{result}' (需要4位字母数字)")
            except ImportError:
                safe_print("  [OCR] ddddocr 未安装，将需要手动输入验证码")
            except Exception as e:
                safe_print(f"  [OCR] 识别异常：{e}")
        except Exception as e:
            safe_print(f"  [OCR] 验证码识别失败：{e}")
        return None

    async def login(self, page) -> bool:
        username = self.config_manager.get_sc_config("username", "hsa697")
        password = self.secure_manager.load_password("scm") or self.config_manager.get_sc_config("password")
        if not password:
            safe_print("[SCM] [FAIL] 密码未找到，请先运行 secure_config.py")
            return False

        safe_print("  [登录] 打开SCM登录页...")
        await page.goto(SCM_URL, timeout=120000)
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(2)

        if await self.is_logged_in(page):
            safe_print("  [登录] 已登录状态")
            return True

        try:
            el = await page.wait_for_selector("#username", timeout=10000)
            await el.click()
            await el.fill("")
            await el.fill(username)
            safe_print("  [登录] [OK] 已填用户名")
        except Exception:
            safe_print("  [登录] [FAIL] 未找到用户名输入框")
            return False

        try:
            el = await page.wait_for_selector("#password", timeout=5000)
            await el.fill("")
            await el.fill(password)
            safe_print("  [登录] [OK] 已填密码")
        except Exception:
            safe_print("  [登录] [FAIL] 未找到密码输入框")
            return False

        try:
            await page.wait_for_selector("#kaptcha", timeout=5000)
        except Exception:
            safe_print("  [登录] [FAIL] 未找到验证码输入框")
            return False

        captcha = None
        for attempt in range(1, 4):
            safe_print(f"  [登录] OCR验证码 (第{attempt}次)...")
            if attempt > 1:
                try:
                    await page.locator("#changeCode").click(timeout=3000)
                    await asyncio.sleep(1)
                except Exception:
                    pass
            captcha = await self._recognize_captcha(page)
            if captcha:
                break
            safe_print(f"  [登录] 第{attempt}次失败" + ("" if attempt < 3 else "，3次均失败"))

        if not captcha:
            safe_print("\n  OCR 3次失败，请手动输入验证码")
            try:
                await page.screenshot(path=os.path.join(BASE, "scm_captcha.png"))
                safe_print("  已保存验证码截图到 scm_captcha.png")
            except Exception:
                pass
            captcha = input("  请输入验证码: ").strip()

        if captcha:
            el = await page.query_selector("#kaptcha")
            if el:
                await el.fill("")
                await el.fill(captcha)
                safe_print("  [登录] [OK] 已填验证码")

        clicked = False
        for sel in ["input[name='CPCLogin']", ".sub_btn", "input[type='submit']"]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    clicked = True
                    safe_print(f"  [登录] [OK] 点击登录 ({sel})")
                    break
            except Exception:
                continue
        if not clicked:
            safe_print("  [登录] 按回车提交")
            await page.keyboard.press("Enter")

        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3)

        if await self.is_logged_in(page):
            safe_print("\n  [OK] SCM登录成功！")
            return True
        try:
            safe_print(f"  [诊断] URL: {page.url}")
            safe_print(f"  [诊断] Title: {await page.title()}")
            await page.screenshot(path=os.path.join(BASE, "debug_scm_login.png"))
            safe_print("  [诊断] 已保存截图至 debug_scm_login.png")
        except Exception:
            pass
        safe_print("\n  [FAIL] SCM登录可能失败")
        return False

    # ── ExtJS 限域操作工具 ──
    async def _dismiss_all(self, page):
        for _ in range(3):
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
        await page.evaluate("""
            (() => {
                try {
                    var layers = document.querySelectorAll('.x-layer, .x-window, .crisp_menu_list, .x-mask');
                    for (var l of layers) {
                        if (l.style.display !== 'none') l.style.display = 'none';
                    }
                    return true;
                } catch(e) { return false; }
            })()
        """)
        await asyncio.sleep(0.5)

    async def _nav_via_extjs(self, page, accordion_text, menu_text, button_text) -> bool:
        return await page.evaluate(f"""
            (() => {{
                try {{
                    var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true }});
                    var accPanels = document.querySelectorAll('.x-accordion-item');
                    var targetAcc = null;
                    for (var acc of accPanels) {{
                        var hd = acc.querySelector('.x-accordion-hd, .x-panel-header');
                        if (!hd) continue;
                        if (hd.textContent.trim().indexOf({json.dumps(accordion_text)}) !== -1) {{
                            targetAcc = acc;
                            break;
                        }}
                    }}
                    if (!targetAcc) return 'no_accordion';
                    if (targetAcc.classList.contains('x-collapsed')) {{
                        var hd = targetAcc.querySelector('.x-accordion-hd, .x-panel-header');
                        if (hd) hd.dispatchEvent(evt);
                    }}
                    var btns = targetAcc.querySelectorAll('.x-btn, button, [role=button]');
                    var menuBtn = null;
                    for (var b of btns) {{
                        var t = b.textContent || b.innerText || '';
                        if (t.trim().indexOf({json.dumps(menu_text)}) !== -1) {{
                            menuBtn = b;
                            break;
                        }}
                    }}
                    if (!menuBtn) return 'no_menu_btn';
                    menuBtn.dispatchEvent(evt);
                    for (var i = 0; i < 10; i++) {{
                        var popup = document.querySelector('.crisp_menu_list');
                        if (popup && popup.style.display !== 'none') {{
                            var popBtns = popup.querySelectorAll('button, .x-btn');
                            for (var pb of popBtns) {{
                                var pt = pb.textContent || pb.innerText || '';
                                if (pt.trim() === {json.dumps(button_text)}) {{
                                    pb.dispatchEvent(evt);
                                    return true;
                                }}
                            }}
                            break;
                        }}
                    }}
                    return 'no_button_in_popup';
                }} catch(e) {{ return 'error:' + e.message; }}
            }})()
        """)

    async def _smart_nav_to(self, page, accordion, menu, button) -> bool:
        for attempt in range(3):
            try:
                r = await self._nav_via_extjs(page, accordion, menu, button)
                if r is True:
                    await asyncio.sleep(2)
                    return True
                safe_print(f"    [导航] ExtJS 失败({r})，尝试 CSS 兜底...")
            except Exception as e:
                safe_print(f"    [导航] ExtJS 异常: {e}")
            await self._dismiss_all(page)
            try:
                a = page.locator(f"text={accordion}").first
                await a.click(timeout=5000)
                await asyncio.sleep(1)
                m = page.locator(f"text={menu}").first
                await m.click(timeout=5000)
                await asyncio.sleep(1)
                b = page.locator(f"text={button}").first
                await b.click(timeout=5000)
                await asyncio.sleep(2)
                return True
            except Exception as e:
                safe_print(f"    [导航] CSS 兜底失败: {e}")
                await asyncio.sleep(1)
        return False

    async def _tab_set_value(self, page, name, value):
        r = await page.evaluate(f"""(() => {{
            try {{
                var f = Ext.ComponentQuery.query('textfield[name={json.dumps(name)}]')[0]
                        || Ext.ComponentQuery.query('[name={json.dumps(name)}]')[0];
                if (!f) return 'not found';
                f.setValue({json.dumps(value)});
                f.fireEvent('change', f, {json.dumps(value)});
                return 'OK';
            }} catch(e) {{ return 'err:' + e.message; }}
        }})()""")
        safe_print(f"    [{name}] {r}")
        return r == "OK"

    async def _tab_select_combo(self, page, name, value):
        r = await page.evaluate(f"""(() => {{
            try {{
                var f = Ext.ComponentQuery.query('combo[name={json.dumps(name)}]')[0]
                        || Ext.ComponentQuery.query('[name={json.dumps(name)}]')[0];
                if (!f) return 'not found';
                f.setValue({json.dumps(value)});
                f.fireEvent('change', f, {json.dumps(value)});
                return 'OK';
            }} catch(e) {{ return 'err:' + e.message; }}
        }})()""")
        safe_print(f"    [combo:{name}] {r}")
        return r == "OK"

    async def _tab_click_btn(self, page, text):
        try:
            r = await page.evaluate(f"""(() => {{
                try {{
                    var btns = Ext.ComponentQuery.query('button');
                    for (var i=0;i<btns.length;i++) {{
                        var t = btns[i].text || (btns[i].getText && btns[i].getText()) || '';
                        if (t && t.indexOf({json.dumps(text)}) !== -1) {{
                            btns[i].fireEvent('click', btns[i]);
                            return 'OK';
                        }}
                    }}
                    return 'not found';
                }} catch(e) {{ return 'err:' + e.message; }}
            }})()""")
            safe_print(f"    [立即查询] {r}")
            if r == "OK":
                return True
        except Exception as e:
            safe_print(f"    [立即查询] ExtJS异常: {e}")
        try:
            btn = await page.locator(f"button:has-text('{text}')").first
            await btn.click(timeout=5000)
            safe_print(f"    [立即查询] CSS点击成功")
            return True
        except Exception:
            return False

    async def _tab_clear_date(self, page, name):
        r = await page.evaluate(f"""(() => {{
            try {{
                var f = Ext.ComponentQuery.query('datefield[name={json.dumps(name)}]')[0]
                        || Ext.ComponentQuery.query('[name={json.dumps(name)}]')[0];
                if (!f) return 'not found';
                f.setValue(null);
                f.fireEvent('change', f, null);
                return 'OK';
            }} catch(e) {{ return 'err:' + e.message; }}
        }})()""")
        safe_print(f"    [clear:{name}] {r}")
        return r == "OK"

    async def _tab_org_search(self, page, name, org):
        r = await page.evaluate(f"""(() => {{
            try {{
                var f = Ext.ComponentQuery.query('[name={json.dumps(name)}]')[0];
                if (!f) return 'not found';
                f.setValue({json.dumps(org)});
                f.fireEvent('change', f, {json.dumps(org)});
                if (f.expand && f.getStore) {{
                    try {{
                        f.getStore().load();
                        f.expand();
                        var st = f.getStore();
                        st.each(function(rec) {{
                            var v = rec.get(f.valueField) || rec.get('value') || '';
                            var d = rec.get(f.displayField) || rec.get('text') || '';
                            if (String(v).toUpperCase() === String({json.dumps(org)}).toUpperCase()
                                || (d && d.toUpperCase().indexOf(String({json.dumps(org)}).toUpperCase()) !== -1)) {{
                                f.setValue(rec.get(f.valueField || 'value'));
                                f.fireEvent('select', f, [rec]);
                                f.collapse();
                                return false;
                            }}
                        }});
                    }} catch(e) {{}}
                }}
                return 'OK';
            }} catch(e) {{ return 'err:' + e.message; }}
        }})()""")
        safe_print(f"    [org:{name}={org}] {r}")
        return r == "OK"

    async def _tab_wait_grid(self, page, label, timeout=60000):
        try:
            await page.wait_for_function(
                "document.querySelector('.x-grid-view tbody tr, .x-grid3-row, table.x-grid-table tbody tr') "
                "|| (typeof Ext!=='undefined' && Ext.ComponentQuery.query('gridview').some(function(g){"
                "return g.getStore && g.getStore().getCount()>0;}))",
                timeout=timeout)
            safe_print(f"  [网格] {label} 已就绪")
        except Exception as e:
            safe_print(f"  [网格] {label} 等待超时/异常: {e}")

    async def _extract_grid_json(self, page, timeout=60000):
        try:
            await page.wait_for_function(
                "document.querySelector('.x-grid-view tbody tr, .x-grid3-row') "
                "|| (typeof Ext!=='undefined' && Ext.ComponentQuery.query('gridview').some(function(g){"
                "return g.getStore && g.getStore().getCount()>0;}))",
                timeout=timeout)
        except Exception:
            pass
        return await page.evaluate("(" + EXTRACT_GRID + ")()")

    async def _set_material_filter(self, page, material):
        for name in SCM_MATERIAL_FIELDS:
            try:
                r = await page.evaluate(f"""(() => {{
                    try {{
                        var f = Ext.ComponentQuery.query('textfield[name={json.dumps(name)}]')[0]
                                || Ext.ComponentQuery.query('[name={json.dumps(name)}]')[0];
                        if (!f) return 'not found';
                        f.setValue({json.dumps(material)});
                        f.fireEvent('change', f, {json.dumps(material)});
                        return 'OK';
                    }} catch(e) {{ return 'err:' + e.message; }}
                }})()""")
                if r == "OK":
                    safe_print(f"    [料号] 已设置字段 {name} = {material}")
                    return name
            except Exception:
                continue
        safe_print("    [料号] [WARN] 未找到料号过滤字段，结果可能未按料号过滤")
        return None

    # ── 各任务表单准备 ──
    async def _setup_tab0(self, page, org_code):
        org_code = org_code or self.config_manager.get_sc_config("org_code", "M03")
        await self._tab_org_search(page, "sap_org_code", org_code)
        await self._tab_set_value(page, "maxsearchrltcmt", "99999")
        await self._tab_select_combo(page, "is_close", "否")

    async def _setup_tab1(self, page, org_code):
        org_code = org_code or self.config_manager.get_sc_config("org_code", "M03")
        await self._tab_clear_date(page, "created_date_start")
        await self._tab_clear_date(page, "created_date_end")
        await self._tab_select_combo(page, "received", "未接收")
        await self._tab_org_search(page, "organization_code", org_code)
        await asyncio.sleep(0.3)
        await self._tab_set_value(page, "maxsearchrltcmt", "99999")

    async def _setup_tab2(self, page, org_code):
        org_code = org_code or self.config_manager.get_sc_config("org_code", "M03")
        await self._tab_set_value(page, "mat_type", "10")

    async def _setup_tab3(self, page, org_code):
        org_code = org_code or self.config_manager.get_sc_config("org_code", "M03")
        await self._tab_org_search(page, "sap_org_code", org_code)

    async def _setup_tab4(self, page, org_code):
        org_code = org_code or self.config_manager.get_sc_config("org_code", "M03")
        await self._tab_org_search(page, "organization_code", org_code)

    # ── 结果展示 ──
    def _display_task_result(self, idx, label, material, raw, report):
        display_rows = to_display_rows(raw)
        headers = [c.get("header") for c in raw.get("cols", [])]
        safe_print("\n" + "=" * 64)
        safe_print(f"  {label}  (料号: {material})")
        safe_print(f"  命中数据行数: {len(display_rows)}")
        report.append(f"\n## {label}（料号 {material}）\n")
        report.append(f"- 命中数据行数：**{len(display_rows)}**\n")

        if not display_rows:
            safe_print("  [提示] 未获取到数据，请检查料号是否正确或筛选条件是否过严")
            report.append("> 未获取到数据，请检查料号是否正确或筛选条件是否过严。\n")
            return

        if idx == 0:  # 送货通知单未制单数量
            col = find_col(headers, "未制单")
            if col:
                total, cnt = sum_col(display_rows, col)
                safe_print(f"  >> 送货通知单未制单数量 = {total}  (来自 {cnt} 行, 列: {col})")
                report.append(f"- **送货通知单未制单数量**: `{total}` （列：{col}，{cnt} 行汇总）\n")
            else:
                safe_print("  [WARN] 未找到含'未制单'的列，无法汇总，请人工核对下方表格")
                report.append("> 未找到含“未制单”的列，请人工核对下方表格。\n")

        elif idx == 1:  # 送货单 未接收已报检 / 未接受未报检
            c1 = find_col(headers, "未接收已报检")
            c2 = find_col(headers, "未接受未报检")
            if c1:
                s1, _ = sum_col(display_rows, c1)
                safe_print(f"  >> 送货单 未接收已报检 数量 = {s1}  (列: {c1})")
                report.append(f"- **未接收已报检 数量**: `{s1}`（列：{c1}）\n")
            else:
                safe_print("  [WARN] 未找到'未接收已报检'列")
            if c2:
                s2, _ = sum_col(display_rows, c2)
                safe_print(f"  >> 送货单 未接受未报检 数量 = {s2}  (列: {c2})")
                report.append(f"- **未接受未报检 数量**: `{s2}`（列：{c2}）\n")
            else:
                safe_print("  [WARN] 未找到'未接受未报检'列")

        elif idx == 2:  # 剩余可发布送货通知总量
            col = find_col(headers, "剩余可发布")
            if col:
                total, cnt = sum_col(display_rows, col)
                safe_print(f"  >> 剩余可发布送货通知总量 = {total}  (来自 {cnt} 行, 列: {col})")
                report.append(f"- **剩余可发布送货通知总量**: `{total}`（列：{col}，{cnt} 行汇总）\n")
            else:
                safe_print("  [WARN] 未找到含'剩余可发布'的列，请人工核对")
                report.append("> 未找到含“剩余可发布”的列，请人工核对下方表格。\n")

        elif idx == 3:  # 回货计划发放：可下发送货通知 是/否
            col = find_col(headers, "可下发送货通知", "可下发")
            if col:
                yes = count_by_value(display_rows, col, "是")
                no = count_by_value(display_rows, col, "否")
                safe_print(f"  >> 可下发送货通知 = 是 : {yes} 行")
                safe_print(f"  >> 可下发送货通知 = 否 : {no} 行")
                report.append(f"- **可下发送货通知 = 是**: `{yes}` 行\n")
                report.append(f"- **可下发送货通知 = 否**: `{no}` 行\n")
            else:
                safe_print("  [WARN] 未找到'可下发送货通知'列")
                report.append("> 未找到“可下发送货通知”列，请人工核对下方表格。\n")

        elif idx == 4:  # 请购单 行状态=下达 总数量
            col = find_col(headers, "行状态", "状态")
            if col:
                dl = [r for r in display_rows if str(r.get(col, "")).strip() == "下达"]
                qcol = find_col(headers, "申请数量", "计划数量", "数量", "采购数量")
                if qcol:
                    s, _ = sum_col(dl, qcol)
                    safe_print(f"  >> 行状态=下达 的请购单行数 = {len(dl)}，对应数量({qcol})合计 = {s}")
                    report.append(f"- **行状态=下达 的请购单行数**: `{len(dl)}`\n")
                    report.append(f"- **对应数量合计**: `{s}`（列：{qcol}）\n")
                else:
                    safe_print(f"  >> 行状态=下达 的请购单行数 = {len(dl)}")
                    report.append(f"- **行状态=下达 的请购单行数**: `{len(dl)}`\n")
            else:
                safe_print("  [WARN] 未找到'行状态'列")
                report.append("> 未找到“行状态”列，请人工核对下方表格。\n")

        # 展示简表（前 30 行）
        if headers:
            safe_print("  ---- 数据明细（前30行）----")
            print_table(headers, [list(r.values()) for r in display_rows[:30]], max_rows=30)
            report.append("\n" + self._md_table(headers, display_rows[:50]) + "\n")

    def _md_table(self, headers, rows):
        if not headers:
            return ""
        lines = ["| " + " | ".join(str(h) for h in headers) + " |",
                 "| " + " | ".join("---" for _ in headers) + " |"]
        for r in rows:
            lines.append("| " + " | ".join(str(r.get(h, "")) for h in headers) + " |")
        return "\n".join(lines)

    # ── 主流程 ──
    async def query_scm(self, context, page, material, org_code=None):
        await load_storage_state(context, STORAGE_FILE_SCM)
        if not await self.login(page):
            safe_print("[SCM] [FAIL] 登录失败，终止 SCM 查询")
            return
        try:
            await save_storage_state(context, STORAGE_FILE_SCM)
        except Exception:
            pass

        tasks = [
            (0, "送货通知查询", self._setup_tab0),
            (1, "送货单查询", self._setup_tab1),
            (2, "采购订单未结量物料汇总查询", self._setup_tab2),
            (3, "回货计划/发放", self._setup_tab3),
            (4, "请购单查询", self._setup_tab4),
        ]
        report = []
        report.append("# SCM 系统查询结果\n")
        report.append(f"- 料号：**{material}**\n")
        for nav_idx, label, setup in tasks:
            safe_print(f"\n{'#'*64}\n# {label}\n{'#'*64}")
            if not await self._smart_nav_to(page, *NAV_CONFIG[nav_idx]):
                safe_print(f"  [FAIL] 导航到 {label} 失败，跳过")
                report.append(f"\n## {label}\n> 导航失败\n")
                continue
            await setup(page, org_code)
            await self._set_material_filter(page, material)
            await self._tab_click_btn(page, "立即查询")
            await self._tab_wait_grid(page, label)
            raw = await self._extract_grid_json(page)
            self._display_task_result(nav_idx, label, material, raw, report)

        md_path = os.path.join(BASE, "scm_query_result.md")
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(report))
            safe_print(f"\n[SCM] 结果已写入: {md_path}")
        except Exception as e:
            safe_print(f"[SCM] 写markdown失败: {e}")


# ── 帆软查询 ──────────────────────────────────────────────
class QueryFanruan:
    def __init__(self, config_manager, secure_manager):
        self.config_manager = config_manager
        self.secure_manager = secure_manager

    async def _login_via_api(self, context, page, username, password) -> bool:
        safe_print("  [帆软] 尝试API登录...")
        result = await page.evaluate(f"""async () => {{
            try {{
                const resp = await fetch('/decision/login', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{username: '{username}', password: '{password}'}})
                }});
                const data = await resp.json();
                if (data.data?.accessToken) {{
                    return {{ok: true, token: data.data.accessToken}};
                }}
                return {{ok: false, error: 'no token'}};
            }} catch(e) {{
                return {{ok: false, error: e.toString()}};
            }}
        }}""")
        if not (result.get("ok") and result.get("token")):
            safe_print(f"  [帆软] API获取token失败: {result}")
            return False
        token = result["token"]
        await page.evaluate("""(token) => {
            ['fine_auth_token','dec_auth_token','accessToken','token',
             'FR_AUTH_TOKEN','FR_TOKEN','fine_token'].forEach(
                k => localStorage.setItem(k, token));
            const expires = new Date(Date.now() + 86400000).toUTCString();
            ['fine_auth_token','dec_auth_token','token'].forEach(k => {
                document.cookie = k + '=' + token + '; expires=' + expires + '; path=/';
            });
        }""", token)
        await context.add_cookies([
            {"name": "fine_auth_token", "value": token, "domain": ".rpt.whirlpool-china.com", "path": "/"},
            {"name": "dec_auth_token", "value": token, "domain": ".rpt.whirlpool-china.com", "path": "/"},
            {"name": "token", "value": token, "domain": ".rpt.whirlpool-china.com", "path": "/"},
        ])
        await page.set_extra_http_headers({"Authorization": f"Bearer {token}"})
        safe_print("  [帆软] token已注入")
        return True

    async def _login_via_form(self, page, username, password) -> bool:
        safe_print("  [帆软] 尝试填表登录...")
        await page.goto(f"{FANRUAN_BASE_URL}/login", timeout=30000)
        await asyncio.sleep(3)
        filled = await page.evaluate("""(args) => {
            const u = document.querySelector('input[placeholder="用户名"]');
            const p = document.querySelector('input[placeholder="密码"]');
            if (!u || !p) return false;
            u.value = args.username; u.dispatchEvent(new Event('input', {bubbles: true}));
            p.value = args.password; p.dispatchEvent(new Event('input', {bubbles: true}));
            return true;
        }""", {"username": username, "password": password})
        if not filled:
            safe_print("  [帆软] 未找到登录表单输入框")
            return False
        await asyncio.sleep(1)
        clicked = False
        for sel in ["div.login-button", "button:has-text('登录')", "button:has-text('Login')", "[class*='login-button']"]:
            try:
                btn = await page.query_selector(sel)
                if btn:
                    await btn.click()
                    clicked = True
                    safe_print("  [帆软] 已点击登录按钮")
                    break
            except Exception:
                continue
        if not clicked:
            safe_print("  [帆软] 按回车提交")
            await page.keyboard.press("Enter")
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        ok = "login" not in page.url.lower()
        if ok:
            safe_print("  [帆软] [OK] 填表登录成功")
        return ok

    async def login_for_page(self, context, page, report_url) -> bool:
        username = self.config_manager.get_fanruan_config("username", "HSA697")
        password = self.secure_manager.load_password("fanruan") or self.config_manager.get_fanruan_config("password")
        await page.goto(report_url, timeout=60000)
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        if "login" in page.url.lower():
            safe_print("  [帆软] 检测到登录页...")
            if not username or not password:
                safe_print("  [帆软] 密码未找到，请先运行 secure_config.py")
                return False
            if await self._login_via_api(context, page, username, password):
                safe_print("  [帆软] API登录成功")
            elif await self._login_via_form(page, username, password):
                safe_print("  [帆软] 填表登录成功")
            else:
                safe_print("  [帆软] 所有登录方式均失败")
                return False
            await page.goto(report_url, timeout=60000)
            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
        try:
            await page.wait_for_function("typeof _g === 'function'", timeout=15000)
            safe_print("  [报表] _g() 就绪")
        except Exception:
            safe_print("  [报表] _g() 未就绪，继续")
        return True

    async def _set_widget(self, page, wname, value):
        r = await page.evaluate(f"""(() => {{
            try {{
                var w = _g().parameterEl.getWidgetByName('{wname}');
                if (w) {{ w.setValue('{value}'); w.fireEvent('afteredit','{value}'); return 'OK'; }}
            }} catch(e) {{}}
            return 'not found';
        }})()""")
        return r == "OK"

    async def _select_factory(self, page, factory_code, factory_text="洗衣机三工厂"):
        for wname in ["P_ORGID", "ORGID", "ORG_ID", "orgid", "P_DEPTID", "FACTORY", "factory"]:
            try:
                r = await page.evaluate(f"""(() => {{
                    try {{
                        var w = _g().parameterEl.getWidgetByName('{wname}');
                        if (w) {{ w.setValue('{factory_code}'); w.fireEvent('afteredit','{factory_code}'); return 'OK'; }}
                    }} catch(e) {{}}
                    return 'not found';
                }})()""")
                if "not found" not in r:
                    safe_print(f"    [{wname}] 已设置")
                    await asyncio.sleep(1)
                    return True
            except Exception:
                continue
        try:
            r = await page.evaluate(f"""(() => {{
                var ss = document.querySelectorAll('select');
                for (var s of ss) {{
                    for (var o of s.options) {{
                        if (o.text.includes('{factory_text}') || o.value === '{factory_code}') {{
                            s.value = o.value; s.dispatchEvent(new Event('change',{{bubbles:true}})); return 'OK';
                        }}
                    }}
                }}
                return 'not found';
            }})()""")
            if "not found" not in r:
                await asyncio.sleep(1)
                return True
        except Exception:
            pass
        return False

    async def _click_query(self, page) -> bool:
        try:
            r = await page.evaluate("""(() => {
                for (var n of ['SEARCH','search','QUERY','query','RUN','run','查询','提交']) {
                    try { var w = _g().parameterEl.getWidgetByName(n); if (w) { w.fireEvent('click'); return 'OK'; } } catch(e) {}
                }
                try { _g().parameterCommit(); return 'commit'; } catch(e) {}
                return 'not found';
            })()""")
            if "not found" not in r:
                return True
        except Exception:
            pass
        for text in ["查询", "运行", "搜索", "Run", "Search", "Query", "提交"]:
            try:
                btn = await page.query_selector(f"button:has-text('{text}'), a:has-text('{text}')")
                if btn:
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    async def _extract_grid_json(self, page, timeout=60000):
        try:
            await page.wait_for_selector(".x-grid-view", timeout=timeout)
        except Exception:
            pass
        return await page.evaluate("(" + EXTRACT_GRID + ")()")

    async def query_fanruan(self, context, page, material, org=None, bin_loc=None):
        await load_storage_state(context, STORAGE_FILE_FR)
        if not await self.login_for_page(page, STOCK_REPORT_URL):
            safe_print("[帆软] 登录失败，终止查询")
            return
        try:
            await save_storage_state(context, STORAGE_FILE_FR)
        except Exception:
            pass

        await asyncio.sleep(2)

        # 料号
        set_item = False
        for w in FR_ITEM_WIDGETS:
            if await self._set_widget(page, w, material):
                safe_print(f"    [帆软] 料号已写入控件 {w} = {material}")
                set_item = True
                break
        if not set_item:
            safe_print("    [WARN] 未找到料号参数控件(尝试了 P_ITEMID 等)，请人工核对参数名")

        # 组织/工厂
        if org:
            if await self._select_factory(page, org):
                safe_print(f"    [帆软] 已设置组织/工厂 = {org}")
            else:
                safe_print(f"    [WARN] 未找到组织参数控件，组织 {org} 未应用")

        # 货位
        if bin_loc:
            set_bin = False
            for w in FR_BIN_WIDGETS:
                if await self._set_widget(page, w, bin_loc):
                    safe_print(f"    [帆软] 货位已写入控件 {w} = {bin_loc}")
                    set_bin = True
                    break
            if not set_bin:
                safe_print(f"    [WARN] 未找到货位参数控件，货位 {bin_loc} 未应用")

        if await self._click_query(page):
            safe_print("    [帆软] 已点击查询")
        else:
            safe_print("    [帆软] [WARN] 未找到查询按钮")
        await asyncio.sleep(4)

        raw = await self._extract_grid_json(page)
        self._display_fanruan(material, org, bin_loc, raw)

    def _display_fanruan(self, material, org, bin_loc, raw):
        display_rows = to_display_rows(raw)
        headers = [c.get("header") for c in raw.get("cols", [])]
        safe_print("\n" + "=" * 64)
        safe_print(f"  帆软 库存报表  (料号: {material}"
                   + (f", 组织: {org}" if org else "")
                   + (f", 货位: {bin_loc}" if bin_loc else "") + ")")
        safe_print(f"  命中数据行数: {len(display_rows)}")

        report = ["# 帆软 库存报表查询结果\n",
                  f"- 料号：**{material}**\n"]
        if org:
            report.append(f"- 组织/工厂：`{org}`\n")
        if bin_loc:
            report.append(f"- 货位：`{bin_loc}`\n")
        report.append(f"- 命中数据行数：**{len(display_rows)}**\n")

        if display_rows:
            col = find_col(headers, "库存现有量", "现有量", "现有库存")
            if col:
                total, cnt = sum_col(display_rows, col)
                safe_print(f"\n  >> 库存现有量 合计 = {total}  (来自 {cnt} 行, 列: {col})")
                report.append(f"- **库存现有量 合计**: `{total}`（列：{col}，{cnt} 行汇总）\n")
            else:
                safe_print("  [WARN] 未找到'库存现有量'列，请人工核对下方表格")
                report.append("> 未找到“库存现有量”列，请人工核对下方表格。\n")

            # 同时展示该列逐行
            if col:
                safe_print("  ---- 库存现有量逐行 ----")
                for i, r in enumerate(display_rows[:30], 1):
                    safe_print(f"    {i:>3}. {r.get(col)}")
            # 简表
            if headers:
                safe_print("  ---- 数据明细（前30行）----")
                print_table(headers, [list(r.values()) for r in display_rows[:30]], max_rows=30)
                lines = ["| " + " | ".join(str(h) for h in headers) + " |",
                         "| " + " | ".join("---" for _ in headers) + " |"]
                for r in display_rows[:50]:
                    lines.append("| " + " | ".join(str(r.get(h, "")) for h in headers) + " |")
                report.append("\n" + "\n".join(lines) + "\n")
        else:
            safe_print("  [提示] 未获取到数据，请检查料号/组织/货位是否正确")
            report.append("> 未获取到数据，请检查料号/组织/货位是否正确。\n")

        md_path = os.path.join(BASE, "fanruan_query_result.md")
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write("\n".join(report))
            safe_print(f"\n[帆软] 结果已写入: {md_path}")
        except Exception as e:
            safe_print(f"[帆软] 写markdown失败: {e}")


# ── 入口 ──────────────────────────────────────────────
async def main_async(args):
    check_dependencies()
    browser = await create_browser(headless=is_headless())
    context = await browser.new_context(accept_downloads=True, ignore_https_errors=True)

    cm = ConfigManager(CONFIG_PATH)
    sm = SecurePasswordManager(cm)

    if args.module in ("fanruan", "all"):
        page = await context.new_page()
        fr = QueryFanruan(cm, sm)
        await fr.query_fanruan(context, page, args.material, args.org, args.bin)
        await page.close()

    if args.module in ("scm", "all"):
        page = await context.new_page()
        scm = QuerySCM(cm, sm)
        await scm.query_scm(context, page, args.material, args.org)
        await page.close()

    await browser.close()
    safe_print("\n[完成] 查询结束")


def main():
    parser = argparse.ArgumentParser(
        description="查询并展示 帆软库存报表 与 SCM 系统数据")
    parser.add_argument("--material", required=True, help="料号（必填）")
    parser.add_argument("--org", default=None,
                        help="组织/工厂代码（可选，帆软作为工厂、SCM作为组织覆盖）")
    parser.add_argument("--bin", "--location", dest="bin", default=None,
                        help="货位（可选，仅帆软库存报表使用）")
    parser.add_argument("--module", choices=("fanruan", "scm", "all"), default="all",
                        help="查询模块，默认 all")
    args = parser.parse_args()

    if "，".encode() in args.material.encode("utf-8"):
        safe_print("[WARN] 检测到中文逗号，已忽略（料号应仅含英文逗号/无分隔符）")

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        safe_print("\n[中断] 用户取消")
    except Exception as e:
        safe_print(f"[FATAL] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
