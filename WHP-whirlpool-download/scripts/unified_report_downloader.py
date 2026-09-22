#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════╗
║  统一报表下载工具 V2.2                               ║
║  执行顺序：SCM → OA → 帆软                           ║
║  密码加密存储（AES-256 via SecurePasswordManager）    ║
║                                                      ║
║  功能模块：                                          ║
║    1. SCM 供应链系统（优化版：ExtJS API + 齐射收网）  ║
║    2. OA 系统（生产计划抓取 → 计划.xlsx）             ║
║    3. 帆软报表系统（report1/2/stock + BOM循环查询）   ║
╚══════════════════════════════════════════════════════╝

用法:
  先运行 python download_secure_config.py 输入密码加密存储
  再运行 python unified_report_downloader.py 执行下载
"""

import asyncio
import base64
import json
import os
import sys
import traceback
from datetime import datetime, date
from io import StringIO
from typing import Dict, List, Optional, Any

# 行缓冲输出
sys.stdout.reconfigure(line_buffering=True)

import urllib3
import pandas as pd
from playwright.async_api import async_playwright

from whirlpool_common import (
    create_browser, decode_local_password, safe_print, Stopwatch,
    save_storage_state, load_storage_state,
    STORAGE_FILE_SCM, STORAGE_DIR,
    check_dependencies as _check_deps,
)
from download_secure_config import ConfigManager, SecurePasswordManager

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ═══════════════════════════════════════════════════════
# 系统常量
# ═══════════════════════════════════════════════════════

SCM_URL = "https://scm.whirlpool-china.com:7580/websrm/"
OA_LOGIN_URL = "https://oa.whirlpool-china.com/wui/index.html#/?_key=gbv4tp"
OA_PLAN_URL = "https://oa.whirlpool-china.com/sanyorpt/product/planview.jsp"
FANRUAN_BASE_URL = "https://rpt.whirlpool-china.com:7027/decision"
REPORT1_URL = f"{FANRUAN_BASE_URL}/v10/entry/access/ece5dd7b-bb69-4072-8b54-807f4c03c0f4?width=1680&height=856"
REPORT2_URL = f"{FANRUAN_BASE_URL}/v10/entry/access/a739cf32-fc07-4a34-905f-43af84e0b4f9?width=1680&height=856"
BOM_REPORT_URL = f"{FANRUAN_BASE_URL}/v10/entry/access/old-platform-reportlet-entry-366?width=1467&height=843"
STOCK_REPORT_URL = f"{FANRUAN_BASE_URL}/v10/entry/access/old-platform-reportlet-entry-573?width=2320&height=1376"

# 帆软导出等待时长（2026-09-19 调长：报表1「已发放工单推式料发料明细」连续报
# 「JS导出超时 / 文件检测超时」，原值 12s 与 18s 不够用）
#   一次导出 = JS_CB_TIMEOUT + POLL_TRIES×POLL_INTERVAL，最坏 120s + 120s = 240s
FANRUAN_EXPORT_JS_TIMEOUT = 120        # JS 下载回调等待，原 12
FANRUAN_EXPORT_POLL_INTERVAL = 0.3     # 落盘轮询间隔（秒），原 0.3
FANRUAN_EXPORT_POLL_TRIES = 400        # 落盘轮询次数，原 60（0.3×60=18s → 0.3×400=120s）


# OA 年月自动计算
def _auto_year_months():
    """自动取当前月和次月（跨年正确处理）"""
    now = date.today()
    cur_year, cur_month = now.year, now.month
    next_month = cur_month + 1 if cur_month < 12 else 1
    next_year = cur_year if cur_month < 12 else cur_year + 1
    return [(cur_year, str(cur_month).zfill(2)), (next_year, str(next_month).zfill(2))]


# ═══════════════════════════════════════════════════════
# SCM 系统模块（优化版：ExtJS API + 网格直提 + 齐射收网）
# ═══════════════════════════════════════════════════════

class SCMSystem:
    """SCM 供应链管理系统 - 优化版（ExtJS API导航 + 网格直提 + 齐射收网）"""

    EXTRACT_GRID = r"""() => {
        // ExtJS 提取
        var tp=Ext.ComponentQuery.query('tabpanel')[0]; var tab=tp?tp.getActiveTab():null; var c=tab||document;
        var gs=c.query?c.query('grid'):Ext.ComponentQuery.query('grid');
        var b=null,bc=0; for(var g of gs){var s=g.getStore&&g.getStore();if(s){var c2=s.getCount();if(c2>bc){bc=c2;b=g;}}}
        if(b&&bc>0) {
            var st=b.getStore(),data=[]; st.each(function(r){data.push(r.data);});
            var cols=[];
            try {
                var v=b.getView();
                if(v){
                    var cm=v.getHeaderCt?v.getHeaderCt():v.headerCt||null;
                    if(cm&&cm.getVisibleGridColumns)cm.getVisibleGridColumns().forEach(function(c){
                        var di=c.dataIndex||c.text||'';
                        if(di && di!=='&#160;') cols.push({key:di,header:c.text||di});
                    });
                }
            } catch(e){}
            if(cols.length>0 || bc>0) {
                if(cols.length===0) return JSON.stringify({e:'extjs_nocols_'+bc});
                return JSON.stringify({rc:bc,cols:cols,data:data});
            }
        }
        // DOM 兜底
        try {
            var v=document.querySelector('.x-grid-view'); if(!v) return JSON.stringify({e:'nodata'});
            var rows=v.querySelectorAll('.x-grid-row'); if(!rows||rows.length===0) return JSON.stringify({e:'nodata'});
            var h=document.querySelector('.x-grid-header-ct'); var cols=[];
            if(h){var hcs=h.querySelectorAll('.x-column-header'); for(var hc of hcs){
                var t=hc.getAttribute('data-headertext')||'';
                if(!t){var ts=hc.querySelector('.x-column-header-text'); if(ts)t=ts.textContent.trim();}
                if(!t)t=hc.textContent.trim();
                if(t&&t!=='&#160;')cols.push(t);
            }}
            var data=[];
            for(var row of rows){
                var rd={}; var cells=row.querySelectorAll('.x-grid-cell');
                for(var ci=0;ci<cells.length&&ci<cols.length;ci++){rd[cols[ci]]=cells[ci].textContent.trim();}
                data.push(rd);
            }
            return JSON.stringify({rc:data.length,cols:cols,data:data});
        } catch(e){return JSON.stringify({e:e.message});}
    }"""

    NAV_CONFIG = [
        ("供应链管理", "采购管理", "送货通知查询"),
        ("供应链管理", "采购管理", "送货单查询"),
        ("供应链管理", "采购管理", "采购订单未结量物料汇总查询"),
        ("供应链管理", "配送管理", "回货计划发放"),
        ("供应链管理", "采购管理", "请购单查询"),
    ]

    TASKS = [
        ("scm_delivery_note", "送货通知查询",    1),
        ("scm_shipment",      "送货单查询",      2),
        ("scm_po_open_qty",   "PO未结量汇总查询", 3),
        ("scm_return_plan",   "回货计划发放",     4),
        ("scm_pr",            "请购单查询",      5),
    ]

    # Phase 2 收网规格: (tab_index, filename, label, timeout, task_id)
    COLLECT_SPEC = [
        (1, "请购单查询.xlsx",              "请购单查询", 180, "scm_pr"),
        (2, "送货通知查询.xlsx",            "送货通知查询", 120, "scm_delivery_note"),
        (3, "送货单查询.xlsx",              "送货单查询", 120, "scm_shipment"),
        (4, "采购订单未结量物料汇总查询.xlsx", "PO未结量", 120, "scm_po_open_qty"),
        (5, "回货计划发放.xlsx",          "回货计划", 120, "scm_return_plan"),
    ]

    # Phase 1 齐射顺序: (nav_index, method_name, dir_config_key)
    # 请购单最先提交（最慢的查询）
    SUBMIT_ORDER = [
        (4, "_process_tab4", "dir_task5"),
        (0, "_process_tab0", "dir_task1"),
        (1, "_process_tab1", "dir_task2"),
        (2, "_process_tab2", "dir_task3"),
        (3, "_process_tab3", "dir_task4"),
    ]

    def __init__(self, config_manager: ConfigManager, secure_manager: SecurePasswordManager):
        self.config_manager = config_manager
        self.secure_manager = secure_manager

    # ── 登录 ──────────────────────────────────────────────

    async def is_logged_in(self, page) -> bool:
        """检查 SCM 登录状态"""
        try:
            cur = page.url
            if '#appcentral' in cur or 'menu' in cur or 'main' in cur:
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

    async def _recognize_captcha(self, page) -> Optional[str]:
        """OCR 验证码识别（ddddocr）"""
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
            if not b64 or ',' not in b64:
                safe_print("  [OCR] 无法获取验证码图片")
                return None
            img_bytes = base64.b64decode(b64.split(',')[1])
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
        """登录 SCM 系统"""
        username = self.config_manager.get_sc_config("username", "hsa697")
        password = self.secure_manager.load_password("scm") or self.config_manager.get_sc_config("password")
        if not password:
            safe_print("[SCM] [FAIL] 密码未找到，请先运行 download_secure_config.py")
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

        # 填用户名
        try:
            el = await page.wait_for_selector("#username", timeout=10000)
            await el.click()
            await el.fill("")
            await el.fill(username)
            safe_print("  [登录] [OK] 已填用户名")
        except Exception:
            safe_print("  [登录] [FAIL] 未找到用户名输入框")
            return False

        # 填密码
        try:
            el = await page.wait_for_selector("#password", timeout=5000)
            await el.fill("")
            await el.fill(password)
            safe_print("  [登录] [OK] 已填密码")
        except Exception:
            safe_print("  [登录] [FAIL] 未找到密码输入框")
            return False

        # 验证码（OCR 3次，失败后手动输入）
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
                safe_print(f"  [登录] [OK] OCR识别: {captcha}")
                break
            safe_print(f"  [登录] 第{attempt}次失败" + ("" if attempt < 3 else "，3次均失败"))

        if not captcha:
            safe_print("\n  OCR 3次失败，请手动输入验证码")
            try:
                await page.screenshot(path="scm_captcha.png")
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

        # 点击登录
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

        # 等待登录完成
        await asyncio.sleep(5)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3)

        if await self.is_logged_in(page):
            safe_print("\n  [OK] SCM登录成功！")
            return True
        # 登录失败诊断
        try:
            safe_print(f"  [诊断] URL: {page.url}")
            safe_print(f"  [诊断] Title: {await page.title()}")
            await page.screenshot(path="debug_scm_login.png")
            safe_print("  [诊断] 已保存截图至 debug_scm_login.png")
        except Exception:
            pass
        safe_print("\n  [FAIL] SCM登录可能失败")
        return False

    # ── ExtJS 限域操作工具 ──────────────────────────────────

    async def _dismiss_all(self, page):
        """清除弹窗/蒙层，确保菜单可见"""
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
        """用 ExtJS API 导航，直接操控组件，不依赖 CSS 可见性"""
        return await page.evaluate(f"""
            (() => {{
                try {{
                    var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true }});

                    // 1. 找 accordion
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

                    // 2. 展开 accordion
                    if (targetAcc.classList.contains('x-collapsed')) {{
                        var hd = targetAcc.querySelector('.x-accordion-hd, .x-panel-header');
                        if (hd) hd.dispatchEvent(evt);
                    }}

                    // 3. 找菜单按钮
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

                    // 4. 点菜单按钮触发 crisp_menu_list
                    menuBtn.dispatchEvent(evt);

                    // 5. 在 crisp_menu_list 中找功能按钮
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

    async def _smart_nav_to(self, page, accordion_text, menu_text, button_text):
        """免刷新导航（ExtJS API 优先，DOM 回退）"""
        await self._dismiss_all(page)
        await asyncio.sleep(1)

        for attempt in range(3):
            result = await self._nav_via_extjs(page, accordion_text, menu_text, button_text)
            if result is True:
                safe_print(f"  [导航] [OK] {button_text}（ExtJS）")
                await self._dismiss_all(page)
                await asyncio.sleep(2)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                return True

            safe_print(f"  [导航] 第{attempt+1}次 ExtJS 失败: {result}")
            await self._dismiss_all(page)
            await asyncio.sleep(1)

        # ExtJS 全部失败 → DOM 方式
        safe_print(f"  [导航] ExtJS 3次均失败，使用 DOM 方式...")
        for attempt in range(3):
            try:
                await self._dismiss_all(page)
                loc = page.locator(f"text={accordion_text}").first
                await loc.wait_for(state="attached", timeout=5000)
                await loc.click()
                await asyncio.sleep(1.5)

                loc = page.locator(f"text={menu_text}").first
                await loc.wait_for(state="attached", timeout=5000)
                await loc.click()
                await asyncio.sleep(1.0)

                popup = page.locator(".crisp_menu_list")
                await popup.wait_for(state="attached", timeout=8000)
                btn = page.locator('.crisp_menu_list button, .crisp_menu_list .x-btn').filter(
                    has_text=button_text
                ).first
                await btn.wait_for(state="attached", timeout=5000)
                await btn.click(force=True)
                safe_print(f"  [导航] [OK] {button_text}（DOM）")
                await self._dismiss_all(page)
                await asyncio.sleep(2)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await asyncio.sleep(2)
                return True
            except Exception as e:
                safe_print(f"  [导航] DOM第{attempt+1}次失败: {e}")
                await self._dismiss_all(page)
                await asyncio.sleep(1)

        safe_print(f"  [导航] [FAIL] {button_text}，全部失败")
        return False

    async def _tab_activate(self, page, index: int) -> bool:
        """切换到指定页签，返回 False = 页签不存在需独立导航"""
        for attempt in range(5):
            try:
                await asyncio.sleep(1)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass

                result = await page.evaluate(f"""
                    (() => {{
                        try {{
                            var tp = Ext.ComponentQuery.query('tabpanel')[0];
                            if (!tp) return 'no_tabpanel';
                            if (tp.items.getCount() <= {index}) return 'not_enough_tabs:' + tp.items.getCount();
                            tp.setActiveTab({index});
                            return 'ok:' + tp.getActiveTab().title;
                        }} catch(e) {{ return 'error:' + e.message; }}
                    }})()
                """)
                if result and result.startswith('ok:'):
                    await asyncio.sleep(0.8)
                    safe_print(f"  [页签] 已激活 {index} ({result[3:]})")
                    return True
                if result and result.startswith('not_enough_tabs'):
                    safe_print(f"  [页签] 标签数不足 ({result})，需要独立导航")
                    return False
                if attempt < 4:
                    safe_print(f"  [页签] 重试 (第{attempt+1}次): {result}")
                    await asyncio.sleep(2)
                    continue
                safe_print(f"  [页签] 无法激活: {result}")
                return False
            except Exception as e:
                msg = str(e)
                if "Execution context was destroyed" in msg:
                    safe_print(f"  [页签] context 销毁 (第{attempt+1}次)...")
                    await asyncio.sleep(3)
                    continue
                safe_print(f"  [页签] 异常: {msg}")
                return False
        return False

    async def _tab_set_value(self, page, field_name: str, value: str) -> bool:
        """在激活页签中用 ExtJS 设置表单字段值"""
        esc_value = json.dumps(value)
        return await page.evaluate(f"""
            (() => {{
                try {{
                    var tp = Ext.ComponentQuery.query('tabpanel')[0];
                    var tab = tp ? tp.getActiveTab() : null;
                    if (!tab) return false;
                    var field = tab.down('[name="{field_name}"]');
                    if (!field) return false;
                    if (field.isXType('datefield')) {{
                        field.setValue(new Date({esc_value}));
                    }} else if (field.isXType('combo')) {{
                        field.setValue({esc_value});
                    }} else if (field.isXType('numberfield')) {{
                        field.setValue(Number({esc_value}));
                    }} else {{
                        field.setValue({esc_value});
                    }}
                    field.fireEvent('change', field, field.getValue());
                    return true;
                }} catch(e) {{ return false; }}
            }})()
        """)

    async def _tab_select_combo(self, page, field_name: str, option_text: str) -> bool:
        """ExtJS 下拉框选择：展开 → 选值"""
        return await page.evaluate(f"""
            (() => {{
                try {{
                    var tp = Ext.ComponentQuery.query('tabpanel')[0];
                    var tab = tp ? tp.getActiveTab() : null;
                    if (!tab) return false;
                    var combo = tab.down('combo[name="{field_name}"]');
                    if (!combo) combo = tab.down('[name="{field_name}"]');
                    if (!combo) return false;
                    combo.expand();
                    var picker = combo.getPicker();
                    if (picker) {{
                        var rec = picker.getStore().findRecord(picker.displayField, {json.dumps(option_text)});
                        if (rec) {{
                            combo.select(rec);
                            return true;
                        }}
                    }}
                    combo.setValue({json.dumps(option_text)});
                    combo.fireEvent('change', combo, combo.getValue());
                    return true;
                }} catch(e) {{ return false; }}
            }})()
        """)

    async def _tab_click_btn(self, page, button_text: str) -> bool:
        """在激活页签中找按钮并点击（ExtJS组件树 → DOM限域 → DOM全局）"""
        # 1. ExtJS 组件树
        ok = await page.evaluate(f"""
            (() => {{
                try {{
                    var tp = Ext.ComponentQuery.query('tabpanel')[0];
                    var tab = tp ? tp.getActiveTab() : null;
                    if (!tab) return false;
                    var btns = tab.query('button, splitbutton');
                    for (var b of btns) {{
                        var t = b.text || (b.getText && b.getText()) || '';
                        if (t.indexOf({json.dumps(button_text)}) !== -1) {{
                            if (b.handler) {{ b.handler.call(b.scope || b, b); return true; }}
                            b.fireEvent('click', b);
                            return true;
                        }}
                    }}
                    return false;
                }} catch(e) {{ return false; }}
            }})()
        """)
        if ok:
            return True

        # 2. DOM 限域（激活页签 body）
        ok = await page.evaluate(f"""
            (() => {{
                try {{
                    var tp = Ext.ComponentQuery.query('tabpanel')[0];
                    var tab = tp ? tp.getActiveTab() : null;
                    if (!tab) return false;
                    var body = tab.getEl ? tab.getEl().dom : null;
                    if (!body) return false;
                    var inners = body.querySelectorAll('.x-btn-inner');
                    for (var el of inners) {{
                        if (el.textContent.trim().indexOf({json.dumps(button_text)}) !== -1) {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }} catch(e) {{ return false; }}
            }})()
        """)
        if ok:
            return True

        # 3. 全局可见按钮兜底
        return await page.evaluate(f"""
            (() => {{
                try {{
                    var inners = document.querySelectorAll('.x-btn-inner');
                    for (var el of inners) {{
                        var txt = el.textContent.trim();
                        if (txt.indexOf({json.dumps(button_text)}) !== -1) {{
                            var rect = el.getBoundingClientRect();
                            if (rect.width > 0 && rect.height > 0) {{
                                el.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }} catch(e) {{ return false; }}
            }})()
        """)

    async def _tab_clear_date(self, page, field_name: str) -> bool:
        """清空日期字段（ExtJS setValue(null)）"""
        return await page.evaluate(f"""
            (() => {{
                try {{
                    var tp = Ext.ComponentQuery.query('tabpanel')[0];
                    var tab = tp ? tp.getActiveTab() : null;
                    if (!tab) return false;
                    var field = tab.down('[name="{field_name}"]');
                    if (!field) return false;
                    field.setValue(null);
                    field.fireEvent('change', field, null);
                    return true;
                }} catch(e) {{ return false; }}
            }})()
        """)

    async def _tab_org_search(self, page, field_name: str, org_code: str) -> bool:
        """组织搜索选择器：ExtJS触发搜索 → Playwright操作弹窗 → 选择 → 确定"""
        # ExtJS 触发搜索按钮
        clicked = await page.evaluate(f"""
            (() => {{
                try {{
                    var tp = Ext.ComponentQuery.query('tabpanel')[0];
                    var tab = tp ? tp.getActiveTab() : null;
                    if (!tab) return false;
                    var field = tab.down('[name="{field_name}"]');
                    if (!field) return false;
                    var el = field.getEl();
                    if (!el) return false;
                    var triggerEl = el.down('.x-form-search-trigger');
                    if (triggerEl) {{
                        triggerEl.dom.click();
                        return true;
                    }}
                    return false;
                }} catch(e) {{ return false; }}
            }})()
        """)
        if not clicked:
            safe_print(f"  [操作] [FAIL] 触发{field_name}搜索失败")
            return False
        await asyncio.sleep(1.5)

        # Playwright 操作弹窗
        try:
            btn = page.locator(
                '.x-window:visible .x-btn-inner:has-text("立即搜索"), '
                '.x-layer:visible .x-btn-inner:has-text("立即搜索")'
            ).first
            if await btn.is_visible(timeout=8000):
                await btn.click(force=True, timeout=5000)
                safe_print("  [操作] [OK] 点击搜索弹窗中的立即搜索")
                await asyncio.sleep(1.5)

            cell = page.locator(
                f'.x-window:visible .x-grid-cell-inner:has-text("{org_code}"), '
                f'.x-layer:visible .x-grid-cell-inner:has-text("{org_code}")'
            ).first
            if await cell.is_visible(timeout=8000):
                await cell.click()
                safe_print(f"  [操作] [OK] 已选组织{org_code}")
                await asyncio.sleep(0.5)

            ok = page.locator(
                '.x-window:visible .x-btn-inner:has-text("确定"), '
                '.x-layer:visible .x-btn-inner:has-text("确定")'
            ).first
            if await ok.is_visible(timeout=5000):
                await ok.click(force=True, timeout=5000)
                safe_print("  [操作] [OK] 确定组织选择")
                await asyncio.sleep(1)
            return True
        except Exception as e:
            safe_print(f"  [操作] [FAIL] 组织搜索弹窗: {e}")
            return False

    async def _tab_wait_grid(self, page, label="查询", timeout=120):
        """等待网格数据就绪（先查数据，无数据时等蒙层消失）"""
        safe_print(f"  [等待] {label}（最长{timeout}s）...")
        for i in range(timeout):
            await asyncio.sleep(1)

            # 1. 先查网格数据
            result = json.loads(await page.evaluate(self.EXTRACT_GRID))
            if not ('e' in result):
                cols, cnt = result.get('cols', []), result.get('rc', 0)
                if cols and cnt > 0:
                    if not (cnt <= 5 and len(cols) <= 3 and i < 60):
                        safe_print(f"  [等待] [OK] 加载完成（约{i}秒，{cnt}行，{len(cols)}列）")
                        return True
                if i >= 10:
                    safe_print(f"  [等待] [WARN] 网格无有效数据（{i}秒），继续")
                    return False

            # 2. 数据未就绪时等蒙层
            if i >= 3:
                loading = await page.evaluate("""() => {
                    try {
                        var masks = document.querySelectorAll('[class*="x-mask"]');
                        for (var m of masks) {
                            if (m.style.display !== "none" && m.offsetParent !== null) return true;
                        }
                        return false;
                    } catch(e) { return false; }
                }""")
                if not loading and i >= 30:
                    safe_print(f"  [等待] [WARN] 网格无数据（{i}秒），继续")
                    return False

        safe_print(f"  [等待] [WARN] 超时（{timeout}s），继续")
        return False

    # ── 导出（浏览器下载捕获） ──────────────────────────────

    async def _extract(self, page, path) -> bool:
        """等待网格数据就绪后，点击导出按钮下载 Excel"""
        # 等待数据加载完成
        for _ in range(12):
            await asyncio.sleep(1)
            c = await page.evaluate("""() => {try{
                var tp=Ext.ComponentQuery.query('tabpanel')[0];var tab=tp?tp.getActiveTab():null;
                if(tab){var gs=tab.query('grid');for(var g of gs){var s=g.getStore&&g.getStore();if(s&&s.getCount()>0)return s.getCount();}}
                var v=document.querySelector('.x-grid-view');if(!v)return 0;
                return v.querySelectorAll('.x-grid-row').length;
            }catch(e){return -1}}""")
            if c > 0:
                break

        download = None
        new_page = None

        async def on_dl(dl):
            nonlocal download
            download = dl
            safe_print(f"  [导出] 捕获下载: {dl.suggested_filename}")

        async def on_page(p):
            nonlocal new_page
            new_page = p
            try:
                title = await p.title()
                safe_print(f"  [导出] 新页面: {title}")
            except Exception:
                pass

        page.on("download", on_dl)
        ctx = page.context
        ctx.on("page", on_page)
        ctx.on("download", on_dl)

        # 点击导出按钮（限域到激活页签）
        clicked = False
        await asyncio.sleep(2)

        # 策略 1: Playwright 等待可见按钮
        for sel in [
            ".x-btn:has-text('导出'):visible",
            "span.x-btn-inner:has-text('导出')",
            "text=导出",
        ]:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(state='visible', timeout=5000)
                await btn.click(force=True, timeout=5000)
                safe_print("  [导出] [OK] 已点击导出")
                clicked = True
                await asyncio.sleep(1)
                break
            except Exception:
                continue

        # 策略 2: ExtJS DOM click
        if not clicked:
            safe_print("  [导出] 尝试 ExtJS DOM click...")
            r = await page.evaluate("""() => {
                try {
                    var tab = Ext.ComponentQuery.query('tabpanel')[0].getActiveTab();
                    var btn = tab.down('[text=导出]') || tab.down('button[text=导出]') || tab.down('splitbutton[text=导出]');
                    if (btn && btn.getEl && btn.getEl().dom) {
                        btn.getEl().dom.click();
                        return 'dom_click';
                    }
                    var all = Ext.ComponentQuery.query('splitbutton').concat(Ext.ComponentQuery.query('button'));
                    for (var i=0;i<all.length;i++) {
                        var t = all[i].text || (all[i].getText && all[i].getText()) || '';
                        if (t.indexOf('导出') !== -1 && all[i].getEl && all[i].getEl().dom) {
                            all[i].getEl().dom.click();
                            return 'dom_click_visible';
                        }
                    }
                    return 'not_found';
                } catch(e) { return 'error:' + e.message; }
            }""")
            safe_print(f"  [导出] ExtJS: {r}")
            if r and 'click' in r:
                clicked = True
                await asyncio.sleep(1)

        # 等待下载触发
        for _ in range(8):
            await asyncio.sleep(1)
            if download or new_page:
                break

        # 等待下载完成
        for _ in range(20):
            await asyncio.sleep(1)
            if download:
                break

        # 保存文件
        result = False
        if download:
            try:
                await download.save_as(path)
                safe_print(f"  [导出] [OK] 已保存: {os.path.basename(path)}")
                result = True
            except Exception as e:
                safe_print(f"  [导出] [FAIL] 保存失败: {e}")
        elif new_page:
            try:
                safe_print(f"  [导出] 新页面: {await new_page.title()}")
            except Exception:
                pass
        else:
            safe_print("  [导出] [WARN] 未捕获下载")

        # 清理监听器
        page.remove_listener("download", on_dl)
        ctx.remove_listener("page", on_page)
        ctx.remove_listener("download", on_dl)
        return result

    # ── 任务1/5：送货通知查询 ──────────────────────────────

    async def _process_tab0(self, page, download_dir, skip_wait=False):
        """送货通知查询"""
        safe_print("\n  [任务1/5] 送货通知查询")
        org_code = self.config_manager.get_sc_config("org_code", "M03")
        await self._tab_org_search(page, "sap_org_code", org_code)
        await self._tab_set_value(page, "maxsearchrltcmt", "99999")
        await self._tab_select_combo(page, "is_close", "否")
        if await self._tab_click_btn(page, "立即查询"):
            safe_print("  [查询] [OK] 已提交查询")
        else:
            safe_print('  [查询] [FAIL] 未找到 立即查询 按钮')
            return
        if skip_wait:
            return
        await self._tab_wait_grid(page, "送货通知查询")
        path = os.path.join(download_dir, "送货通知查询.xlsx")
        if not await self._extract(page, path):
            safe_print("  [导出] [FAIL] 网格无数据")

    # ── 任务2/5：送货单查询 ──────────────────────────────

    async def _process_tab1(self, page, download_dir, skip_wait=False):
        """送货单查询"""
        safe_print("\n  [任务2/5] 送货单查询")
        org_code = self.config_manager.get_sc_config("org_code", "M03")
        start_date = self.config_manager.get_sc_config("shipment_date_start", "2026-07-17")
        end_date = date.today().strftime("%Y-%m-%d")
        await self._tab_set_value(page, "created_date_start", start_date)
        await self._tab_set_value(page, "created_date_end", end_date)
        safe_print(f"  [日期] [OK] 送货单产生日期 {start_date} ~ {end_date}")
        await self._tab_select_combo(page, "received", "未接收")
        await self._tab_org_search(page, "organization_code", org_code)
        await asyncio.sleep(0.3)
        await self._tab_set_value(page, "maxsearchrltcmt", "99999")
        if await self._tab_click_btn(page, "立即查询"):
            safe_print("  [查询] [OK] 已提交查询")
        else:
            safe_print('  [查询] [FAIL] 未找到 立即查询 按钮')
            return
        if skip_wait:
            return
        await self._tab_wait_grid(page, "送货单查询")
        path = os.path.join(download_dir, "送货单查询.xlsx")
        if not await self._extract(page, path):
            safe_print("  [导出] [FAIL] 网格无数据")

    # ── 任务3/5：PO未结量汇总查询 ────────────────────────

    async def _process_tab2(self, page, download_dir, skip_wait=False):
        """PO未结量汇总查询"""
        safe_print("\n  [任务3/5] PO未结量汇总查询")
        org_code = self.config_manager.get_sc_config("org_code", "M03")
        await self._tab_org_search(page, "organization_code", org_code)
        await asyncio.sleep(0.3)
        await self._tab_set_value(page, "maxsearchrltcmt", "99999")
        if await self._tab_click_btn(page, "立即查询"):
            safe_print("  [查询] [OK] 已提交查询")
        else:
            safe_print('  [查询] [FAIL] 未找到 立即查询 按钮')
            return
        if skip_wait:
            return
        await self._tab_wait_grid(page, "PO未结量查询")
        path = os.path.join(download_dir, "采购订单未结量物料汇总查询.xlsx")
        if not await self._extract(page, path):
            safe_print("  [导出] [FAIL] 网格无数据")

    # ── 任务4/5：回货计划发放 ────────────────────────────

    async def _process_tab3(self, page, download_dir, skip_wait=False):
        """回货计划发放"""
        safe_print("\n  [任务4/5] 回货计划发放")

        # 1. 点击筛选按钮
        ok = await self._tab_click_btn(page, "筛选")
        if not ok:
            for s in ['#button-1190', 'a.x-btn:has-text("筛选")', 'span.x-btn-inner:has-text("筛选")']:
                try:
                    fb = page.locator(s).first
                    if await fb.is_visible(timeout=3000):
                        await fb.click(force=True, timeout=5000)
                        ok = True
                        break
                except Exception:
                    continue
        if not ok:
            safe_print("  [操作] [FAIL] 无筛选按钮")
            return
        safe_print("  [操作] [OK] 筛选")
        await asyncio.sleep(2)

        # 2. 清空日期 + 勾选复选框（弹窗是全局的，用 Playwright）
        for name, label in [
            ("created_date", "要求日期-起"),
            ("endcreated_date", "要求日期-止"),
            ("startdate", "开始日期"),
            ("enddate", "结束日期"),
        ]:
            try:
                inp = page.locator(f'input[name="{name}"]').first
                if await inp.is_visible(timeout=3000):
                    await inp.click(click_count=3)
                    await asyncio.sleep(0.15)
                    await page.keyboard.press("Delete")
                    await asyncio.sleep(0.15)
                    await page.keyboard.press("Tab")
                    safe_print(f'  [操作] [OK] 清空{label}')
            except Exception:
                pass

        for cb_name, cb_label in [
            ("deliverinfore_released", "只显示未完全分配的数据"),
            ("filter_zero", "滤掉缺料为0的数据"),
        ]:
            checked = False
            try:
                inp = page.locator(f'input[name="{cb_name}"]').first
                if await inp.is_visible(timeout=2000):
                    if not await inp.is_checked():
                        await inp.check()
                    safe_print(f'  [操作] [OK] 勾选{cb_label}')
                    checked = True
            except Exception:
                pass
            if checked:
                await asyncio.sleep(0.3)
                continue
            # ExtJS 兜底
            ok = await page.evaluate(f"""(() => {{
                try {{
                    var all = Ext.ComponentQuery.query('[name="{cb_name}"]');
                    if (all.length > 0) {{
                        var c = all[0];
                        if (c.setValue) {{ c.setValue(true); return 'extjs'; }}
                    }}
                }} catch(e) {{}}
                return false;
            }})()""")
            if ok:
                safe_print(f'  [操作] [OK] ExtJS勾选{cb_label}')
            else:
                safe_print(f'  [操作] [WARN] 未找到{cb_label}')
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.5)

        # 3. 点筛选弹窗确定
        ok = False
        for s in [
            '.x-window:visible .x-btn-inner:has-text("确定")',
            '.x-layer:visible .x-btn-inner:has-text("确定")',
            'span.x-btn-inner:has-text("确定")',
        ]:
            try:
                loc = page.locator(s).first
                if await loc.is_visible(timeout=5000):
                    await loc.click(force=True, timeout=5000)
                    ok = True
                    safe_print("  [操作] [OK] 确定筛选")
                    break
            except Exception:
                continue
        if not ok:
            safe_print("  [操作] [FAIL] 无法点击确定")
            return

        if skip_wait:
            return
        await self._tab_wait_grid(page, "回货计划查询")
        path = os.path.join(download_dir, "回货计划发放.xlsx")
        if not await self._extract(page, path):
            safe_print("  [导出] [FAIL] 网格无数据")

    # ── 任务5/5：请购单查询 ──────────────────────────────

    async def _process_tab4(self, page, download_dir, skip_wait=False):
        """请购单查询"""
        safe_print("\n  [任务5/5] 请购单查询")
        org_code = self.config_manager.get_sc_config("org_code", "M03")
        audit_date = self.config_manager.get_sc_config("audit_date", "2026-04-01")

        # 清空采购员
        try:
            inp = page.locator('input[name="buyer_code"]').first
            if await inp.is_visible(timeout=3000):
                await inp.click(click_count=3)
                await asyncio.sleep(0.2)
                await page.keyboard.press("Delete")
                await asyncio.sleep(0.2)
                await page.keyboard.press("Tab")
                safe_print('  [操作] [OK] 清空采购员')
        except Exception as e:
            safe_print(f'  [操作] [WARN] 清空采购员: {e}')

        # 设置审核日期
        await self._tab_set_value(page, "podate_start", audit_date)

        # 最大99999
        await self._tab_set_value(page, "maxsearchrltcmt", "99999")

        # 组织搜索
        found = False
        for name in ["organization_code", "sap_org_code", "org_code"]:
            if await self._tab_org_search(page, name, org_code):
                found = True
                break
        if not found:
            safe_print("  [操作] [WARN] 未找到组织字段")

        # 立即查询
        if await self._tab_click_btn(page, "立即查询"):
            safe_print("  [查询] [OK] 已提交查询")
        else:
            safe_print('  [查询] [FAIL] 未找到 立即查询 按钮')
            return

        if skip_wait:
            return
        await self._tab_wait_grid(page, "请购单查询", timeout=180)
        path = os.path.join(download_dir, "请购单查询.xlsx")
        if not await self._extract(page, path):
            safe_print("  [导出] [FAIL] 网格无数据")

    # ── 主执行（齐射收网） ──────────────────────────────

    async def run_all(self, page, context) -> Dict[str, bool]:
        """执行所有 SCM 任务（Cookie恢复→登录→Phase1齐射→Phase2收网）"""
        results = {}

        # ── Cookie 恢复或登录 ──
        logged_in = False
        if await load_storage_state(context, STORAGE_FILE_SCM):
            await page.goto(SCM_URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            if await self.is_logged_in(page):
                safe_print("  [登录] 通过缓存 Cookie 恢复会话成功！")
                logged_in = True

        if not logged_in:
            logged_in = await self.login(page)
            if logged_in:
                await save_storage_state(context, STORAGE_FILE_SCM)

        if not logged_in:
            safe_print("\n[SCM] [FAIL] 登录失败，中止所有任务")
            return {t[0]: False for t in self.TASKS}

        # 确定各任务下载目录
        download_dirs = {}
        for tid, label, num in self.TASKS:
            dir_key = f"dir_task{num}"
            d = self.config_manager.get_sc_config(dir_key, "")
            if not d:
                d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads", f"scm_task{num}")
            os.makedirs(d, exist_ok=True)
            download_dirs[tid] = d

        # ═══ Phase 1: 齐射 — 提交全部查询（不等结果） ═══
        safe_print("\n" + "=" * 50)
        safe_print("  Phase 1: 齐射 — 提交查询（skip_wait）")
        safe_print("=" * 50)

        for idx, (nav_index, method_name, dir_key) in enumerate(self.SUBMIT_ORDER, 1):
            nav_cfg = self.NAV_CONFIG[nav_index]
            accordion, menu, button = nav_cfg
            tid = None
            for t in self.TASKS:
                if f"dir_task{t[2]}" == dir_key:
                    tid = t[0]
                    break
            download_dir = download_dirs.get(tid, "")

            safe_print(f"\n  [{idx}/5] 打开并提交 {button}...")
            ok = await self._smart_nav_to(page, accordion, menu, button)
            if ok:
                await asyncio.sleep(0.3)
                proc_fn = getattr(self, method_name)
                await proc_fn(page, download_dir, skip_wait=True)

        # ═══ Phase 2: 收网 — 逐个收集结果 ═══
        safe_print("\n" + "=" * 50)
        safe_print("  Phase 2: 收网 — 收集数据")
        safe_print("=" * 50)

        # 等待页面稳定
        safe_print("  [收网] 等待页面稳定...")
        for _ in range(10):
            await asyncio.sleep(2)
            try:
                await page.wait_for_load_state("load", timeout=5000)
            except Exception:
                continue
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                continue
            try:
                ok = await page.evaluate("1+1")
                if ok == 2:
                    safe_print("  [收网] 页面已稳定")
                    break
            except Exception:
                continue

        # 切回第一个任务页签
        await self._tab_activate(page, 1)

        ok_count = 0
        fail_count = 0
        for tab_index, filename, label, timeout, task_id in self.COLLECT_SPEC:
            download_dir = download_dirs.get(task_id, "")
            safe_print(f"\n  [收集] 页签{tab_index}: {label}")
            ok = await self._tab_activate(page, tab_index)
            if not ok:
                safe_print(f"  [收集] 页签已丢失，独立导航...")
                # 独立导航兜底
                nav_cfg = self.NAV_CONFIG[
                    4 if task_id == "scm_pr" else
                    0 if task_id == "scm_delivery_note" else
                    1 if task_id == "scm_shipment" else
                    2 if task_id == "scm_po_open_qty" else
                    3
                ]
                accordion, menu, button = nav_cfg
                if await self._smart_nav_to(page, accordion, menu, button):
                    proc_fn_name = self.SUBMIT_ORDER[
                        [s[2] for s in self.SUBMIT_ORDER].index(
                            f"dir_task{[t[2] for t in self.TASKS if t[0]==task_id][0]}"
                        )
                    ][1]
                    proc_fn = getattr(self, proc_fn_name)
                    await proc_fn(page, download_dir, skip_wait=False)
                    ok_count += 1
                    results[task_id] = True
                else:
                    fail_count += 1
                    results[task_id] = False
                continue

            if await self._tab_wait_grid(page, label, timeout=timeout):
                path = os.path.join(download_dir, filename)
                if await self._extract(page, path):
                    safe_print(f"  [收集] [OK] {filename}")
                    ok_count += 1
                    results[task_id] = True
                else:
                    safe_print(f"  [收集] [FAIL] {filename} 导出失败")
                    fail_count += 1
                    results[task_id] = False
            else:
                safe_print(f"  [收集] [SKIP] {filename} 超时/无数据")
                fail_count += 1
                results[task_id] = False

        safe_print("\n" + "=" * 60)
        safe_print(f"  SCM完成！成功{ok_count}个，失败{fail_count}个")
        safe_print("=" * 60)

        return results



# OA 系统模块
# ═══════════════════════════════════════════════════════

class OASystem:
    """OA 系统 - 登录+抓取生产计划+保存 计划.xlsx"""

    def __init__(self, config_manager: ConfigManager, secure_manager: SecurePasswordManager):
        self.config_manager = config_manager
        self.secure_manager = secure_manager
        self.year_months = _auto_year_months()

    async def is_logged_in(self, page) -> bool:
        """检查 OA 登录状态"""
        try:
            inputs = await page.query_selector_all('#loginid, [name="loginid"], input[placeholder*="账号"]')
            pwds = await page.query_selector_all('#userpassword, [name="userpassword"], input[type="password"]')
            if len(inputs) > 0 and len(pwds) > 0:
                return False
            return True
        except Exception:
            return True

    async def login(self, page) -> bool:
        """登录 OA 系统"""
        username = self.config_manager.get_oa_config("username", "hsa697")
        password = self.secure_manager.load_password("oa") or self.config_manager.get_oa_config("password")
        if not password:
            safe_print("[OA] [FAIL] 密码未找到，请先运行 download_secure_config.py")
            return False

        for attempt in range(3):
            if attempt == 0:
                safe_print("  [OA] 打开登录页...")
                await page.goto(OA_LOGIN_URL, timeout=60000)
            else:
                safe_print(f"  [OA] 刷新重试（第{attempt+1}次）...")
                await page.reload(timeout=60000)

            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(2)

            if await self.is_logged_in(page):
                safe_print("  [OA] 已登录状态")
                await page.goto(OA_PLAN_URL, timeout=30000)
                await asyncio.sleep(2)
                return True

            if not username or not password:
                safe_print("  [OA] 未提供凭证")
                if attempt < 2:
                    continue
                return False

            try:
                await page.wait_for_selector("#loginid", timeout=15000)
                break
            except Exception:
                safe_print(f"  [OA] 第{attempt+1}次未检测到登录框")
                if attempt < 2:
                    continue
                return False

        safe_print("  [OA] 填表登录...")
        try:
            await page.fill("#loginid", username)
            await asyncio.sleep(0.3)
            await page.fill("#userpassword", password)
            await asyncio.sleep(0.3)

            clicked = False
            for sel in ["#login", "input[type='submit']", "input[value='登录']"]:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        await btn.click()
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                await page.keyboard.press("Enter")

            safe_print("  [OA] 等待登录完成（5秒稳定期）...")
            await asyncio.sleep(5)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(3)

            if await self.is_logged_in(page):
                safe_print("  [OA] [OK] 登录成功")
                safe_print("  [OA] 跳转计划页...")
                await page.goto(OA_PLAN_URL, timeout=30000)
                await asyncio.sleep(3)
                try:
                    await page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                return True
            else:
                safe_print("  [OA] [FAIL] 登录似乎未成功")
        except Exception as e:
            safe_print(f"  [OA] [FAIL] 登录异常: {e}")
        return False

    async def _scrape(self, page, factory_code) -> Dict[str, Any]:
        """抓取生产计划表格数据，返回 {月份: DataFrame}"""
        try:
            await page.wait_for_selector("#maintable", timeout=15000)
        except Exception:
            safe_print("  [OA] 未找到#maintable")
            return {}

        # 设置工厂
        await page.evaluate(f"""(() => {{
            var s = document.querySelector('[name="orgid"]');
            if (s) {{ s.value = '{factory_code}'; s.dispatchEvent(new Event('change', {{bubbles:true}})); }}
        }})()""")
        await asyncio.sleep(0.3)
        safe_print(f"  [OA] 工厂={factory_code}")

        table_by_month = {}
        for year, month in self.year_months:
            safe_print(f"  [OA] 处理 {year}-{month}...")

            # 设置年份
            await page.evaluate(f"""(() => {{
                var s = document.querySelector('[name="styear"]');
                if (s) {{ s.value = '{year}'; s.dispatchEvent(new Event('change', {{bubbles:true}})); }}
            }})()""")
            await asyncio.sleep(0.2)

            # 设置月份
            await page.evaluate(f"""(() => {{
                var s = document.querySelector('[name="stmon"]');
                if (s) {{ s.value = '{month}'; s.dispatchEvent(new Event('change', {{bubbles:true}})); }}
            }})()""")
            await asyncio.sleep(0.2)

            # 点击提交
            await page.evaluate("""(() => {
                var b = document.querySelector('[name="submitbtn"]');
                if (b) { b.click(); return; }
                var f = document.forms[0]; if (f) f.submit();
            })()""")
            await asyncio.sleep(0.3)

            try:
                await page.wait_for_selector("#maintable", timeout=15000)
            except Exception:
                safe_print(f"  [OA] {month}无表格")
                continue
            await asyncio.sleep(1)

            html = await page.evaluate("() => { var t = document.getElementById('maintable'); return t ? t.outerHTML : ''; }")
            if html:
                df = pd.read_html(StringIO(html))[0].dropna(how="all")
                if len(df) > 0:
                    table_by_month[month] = df
                    safe_print(f"  [OA] {month}: {len(df)}行")

        return table_by_month

    def _save_plan_to_excel(self, month_data, output_dir) -> str:
        """保存计划数据到 Excel"""
        if not month_data:
            return ""
        path = os.path.join(output_dir, "计划.xlsx")
        months_order = [m for _, m in self.year_months]
        ordered = [m for m in months_order if m in month_data]
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            for idx, m in enumerate(ordered):
                sheet = "N" if idx == 0 else f"N+{idx}"
                month_data[m].to_excel(w, sheet_name=sheet, index=False)
                safe_print(f"  [保存] '{sheet}' ({m}月, {len(month_data[m])}行)")
        safe_print(f"  [保存] {path}")
        return path

    async def run(self, page) -> bool:
        """执行 OA 任务：登录 → 抓取 → 保存"""
        plan_dir = self.config_manager.get_oa_config("plan_dir", "")
        if not plan_dir:
            plan_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads", "oa_plan")
        os.makedirs(plan_dir, exist_ok=True)

        # 检查 Excel 是否已存在且较新（1小时内）
        excel_path = os.path.join(plan_dir, "计划.xlsx")
        if os.path.exists(excel_path):
            mtime = os.path.getmtime(excel_path)
            last_update = datetime.fromtimestamp(mtime)
            now = datetime.now()
            if (now - last_update).total_seconds() < 3600:
                safe_print(f"[OA] [OK] 计划.xlsx 已存在（{last_update.strftime('%Y-%m-%d %H:%M')}）")
                return True

        factory_code = self.config_manager.get_oa_config("factory_code", "M03")

        ok = await self.login(page)
        if not ok:
            safe_print("[OA] [FAIL] 登录失败")
            return False

        month_data = await self._scrape(page, factory_code)
        if month_data:
            self._save_plan_to_excel(month_data, plan_dir)
            return True
        else:
            safe_print("[OA] [WARN] 未抓取到任何生产计划数据")
            return False


# ═══════════════════════════════════════════════════════
# 帆软报表系统模块
# ═══════════════════════════════════════════════════════

class FanruanSystem:
    """帆软报表系统 - 登录+4个报表（report1/2/stock/bom）"""

    TASKS = [
        ("report1", "已发放工单推式料发料明细"),
        ("report2", "SCM转订单无效清单"),
        ("stock",   "库存报表"),
        ("bom",     "BOM循环查询"),
    ]

    KEEP_ORIGINAL_NAME = {"已发放工单推式料发料明细", "SCM转订单无效清单", "SCM-转订单无效清单"}

    def __init__(self, config_manager: ConfigManager, secure_manager: SecurePasswordManager):
        self.config_manager = config_manager
        self.secure_manager = secure_manager

    # ── 登录 ──────────────────────────────────────────────

    async def _login_via_api(self, context, page, username, password) -> bool:
        """帆软 API 登录（必须先导航到帆软域名才能 evaluate）"""
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
        safe_print(f"  [帆软] API获取token: {token[:40]}...")

        # 注入 token 到 localStorage 和 cookie
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
            {"name": "dec_auth_token",  "value": token, "domain": ".rpt.whirlpool-china.com", "path": "/"},
            {"name": "token",           "value": token, "domain": ".rpt.whirlpool-china.com", "path": "/"},
        ])

        await page.set_extra_http_headers({"Authorization": f"Bearer {token}"})
        safe_print("  [帆软] token已注入")
        return True

    async def _login_via_form(self, page, username, password) -> bool:
        """帆软表单登录"""
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
        """导航到报表URL，检测登录状态，必要时执行登录"""
        username = self.config_manager.get_fanruan_config("username", "HSA697")
        password = self.secure_manager.load_password("fanruan") or self.config_manager.get_fanruan_config("password")

        await page.goto(report_url, timeout=60000)
        await asyncio.sleep(3)
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass

        # 检查是否需要登录
        if "login" in page.url.lower():
            safe_print("  [帆软] 检测到登录页...")
            if not username or not password:
                safe_print("  [帆软] 密码未找到，请先运行 download_secure_config.py")
                return False
            # 先尝试 API 登录
            if await self._login_via_api(context, page, username, password):
                safe_print("  [帆软] API登录成功")
            elif await self._login_via_form(page, username, password):
                safe_print("  [帆软] 填表登录成功")
            else:
                safe_print("  [帆软] 所有登录方式均失败")
                return False
            # 登录后重新导航到报表
            await page.goto(report_url, timeout=60000)
            await asyncio.sleep(3)
            try:
                await page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass

        # 等待 _g() 就绪
        try:
            await page.wait_for_function("typeof _g === 'function'", timeout=15000)
            safe_print("  [报表] _g() 就绪")
        except Exception:
            safe_print("  [报表] _g() 未就绪，继续")
        return True

    # ── 报表通用操作 ──────────────────────────────────────

    async def _select_factory(self, page, factory_code, factory_text="洗衣机三工厂"):
        """设置帆软报表工厂参数"""
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
        # 尝试 select 下拉
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
        """点击帆软报表查询按钮"""
        # 先尝试 JS API
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
        # 尝试按钮元素
        for text in ["查询", "运行", "搜索", "Run", "Search", "Query", "提交"]:
            try:
                btn = await page.query_selector(f"button:has-text('{text}'), a:has-text('{text}')")
                if btn:
                    await btn.click()
                    return True
            except Exception:
                continue
        return False

    async def _export_report(self, page, download_dir, label, keep_original_name=False, retry=1) -> bool:
        """帆软报表导出（JS API → 文件轮询）"""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in label) or "export"
        target_name = f"{safe}.xlsx"
        target_path = os.path.join(download_dir, target_name)

        for attempt in range(1 + retry):
            if attempt > 0:
                safe_print(f"  [导出] 第{attempt}次重试...")
                await asyncio.sleep(2)
                await self._click_query(page)
                await asyncio.sleep(2)

            if not keep_original_name and os.path.exists(target_path):
                os.remove(target_path)

            existing = set(os.listdir(download_dir))

            # JS API 导出
            future = asyncio.get_event_loop().create_future()
            def on_dl(dl):
                if not future.done():
                    future.set_result(dl)
            page.on('download', on_dl)

            try:
                await page.evaluate("_g().exportReportToExcel('simple')")
                try:
                    dl = await asyncio.wait_for(future, timeout=FANRUAN_EXPORT_JS_TIMEOUT)
                    if keep_original_name:
                        fname = dl.suggested_filename
                        if not fname.endswith('.xlsx'):
                            fname += '.xlsx'
                        save_path = os.path.join(download_dir, fname)
                    else:
                        save_path = target_path
                    await dl.save_as(save_path)
                    safe_print(f"  [导出] {os.path.basename(save_path)}")
                    return True
                except asyncio.TimeoutError:
                    safe_print("  [导出] JS导出超时，尝试文件检测...")
            except Exception:
                pass
            finally:
                page.remove_listener('download', on_dl)

            # 文件轮询检测
            for _ in range(FANRUAN_EXPORT_POLL_TRIES):
                await asyncio.sleep(FANRUAN_EXPORT_POLL_INTERVAL)
                cur = set(os.listdir(download_dir))
                new = cur - existing
                xlsx_new = [f for f in new if f.endswith(".xlsx") and not f.endswith(".crdownload") and not f.endswith(".tmp")]
                if xlsx_new:
                    src = max([os.path.join(download_dir, f) for f in xlsx_new], key=os.path.getmtime)
                    if keep_original_name:
                        safe_print(f"  [导出] (FS) {os.path.basename(src)}")
                    else:
                        if os.path.basename(src) != target_name:
                            if os.path.exists(target_path):
                                os.remove(target_path)
                            os.replace(src, target_path)
                        safe_print(f"  [导出] (FS) {target_name}")
                    return True

            if attempt < retry:
                safe_print(f"  [导出] 第{attempt+1}次尝试失败，重试...")
            else:
                safe_print("  [导出] 文件检测超时")

        return False

    # ── 物料编码读取 ──────────────────────────────────────

    def _get_material_codes_from_simple_excel(self, path) -> List[str]:
        """从简单Excel读取物料编码（第一列，跳过标题行）"""
        try:
            df = pd.read_excel(path, header=None)
            if df.empty:
                return []
            codes = df.iloc[1:, 0].dropna().astype(str).str.strip()
            bad = {"nan", "None", "", "NaN", "null", "NULL", "-"}
            return sorted(set(c for c in codes if c not in bad))
        except Exception as e:
            safe_print(f"  [BOM] 读取Excel失败: {e}")
            return []

    def _get_material_codes_from_excel(self, path) -> List[str]:
        """从OA计划Excel读取物料编码（查找"产品编码"列）"""
        try:
            sheets = pd.read_excel(path, sheet_name=None, header=1)
            codes = []
            for sn, df in sheets.items():
                if df.empty:
                    continue
                col = None
                names = [str(c).strip() for c in df.columns]
                for i, n in enumerate(names):
                    if "产品编码" in n:
                        col = df.columns[i]
                        break
                if col is None:
                    col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
                vals = df[col].dropna().astype(str).str.strip()
                bad = {"nan", "None", "", "NaN", "null", "NULL", "-", "产品编码"}
                vals = [v for v in vals if v not in bad]
                codes.extend(vals)
            return sorted(set(codes))
        except Exception as e:
            safe_print(f"  [BOM] 读取Excel失败: {e}")
            return []

    def _load_material_codes(self) -> List[str]:
        """加载物料编码（优先本地Excel，其次OA计划Excel）"""
        # 优先本地物料文件
        mat_path = self.config_manager.get_fanruan_config("material_excel_path", "").strip()
        if mat_path and os.path.exists(mat_path):
            safe_print(f"  [BOM] 使用本地物料Excel: {mat_path}")
            return self._get_material_codes_from_simple_excel(mat_path)

        # OA 计划输出
        oa_plan_dir = self.config_manager.get_oa_config("plan_dir", "")
        plan_path = os.path.join(oa_plan_dir, "计划.xlsx")
        if os.path.exists(plan_path):
            safe_print(f"  [BOM] 从OA计划读取物料编码: {plan_path}")
            return self._get_material_codes_from_excel(plan_path)

        safe_print("  [BOM] [WARN] 未找到物料编码来源，BOM任务将跳过")
        return []

    # ── 报表1：已发放工单推式料发料明细 ───────────────────

    async def _run_report1(self, page, context, download_dir) -> bool:
        safe_print("\n" + "=" * 50)
        safe_print("报表1: 已发放工单推式料发料明细")
        safe_print("=" * 50)

        ok = await self.login_for_page(context, page, REPORT1_URL)
        if not ok:
            safe_print("  [报表1] 登录失败")
            return False

        factory_code = self.config_manager.get_fanruan_config("factory_code", "664")
        await self._select_factory(page, factory_code)
        await self._click_query(page)

        safe_print("  [等待] 报表加载...")
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3)

        return await self._export_report(page, download_dir, "已发放工单推式料发料明细",
                                          keep_original_name=True)

    # ── 报表2：SCM-转订单无效清单 ─────────────────────────

    async def _run_report2(self, page, context, download_dir) -> bool:
        safe_print("\n" + "=" * 50)
        safe_print("报表2: SCM-转订单无效清单")
        safe_print("=" * 50)

        ok = await self.login_for_page(context, page, REPORT2_URL)
        if not ok:
            safe_print("  [报表2] 登录失败")
            return False

        safe_print("  [等待] 报表加载...")
        try:
            await page.wait_for_load_state("networkidle", timeout=30000)
        except Exception:
            pass
        await asyncio.sleep(3)

        return await self._export_report(page, download_dir, "SCM-转订单无效清单",
                                          keep_original_name=True)

    # ── 报表3：库存报表 ──────────────────────────────────

    async def _run_stock(self, page, context, download_dir) -> bool:
        safe_print("\n" + "=" * 50)
        safe_print("报表3: 库存报表")
        safe_print("=" * 50)

        # 使用独立 page 避免状态污染
        stock_page = await context.new_page()
        try:
            ok = await self.login_for_page(context, stock_page, STOCK_REPORT_URL)
            if not ok:
                safe_print("  [库存报表] 登录失败")
                return False

            safe_print("  [库存报表] 点击查询...")
            await self._click_query(stock_page)
            try:
                await stock_page.wait_for_load_state("networkidle", timeout=30000)
            except Exception:
                pass
            await asyncio.sleep(3)

            ok = await self._export_report(stock_page, download_dir, "库存报表", retry=1)
            if not ok:
                safe_print("  [库存报表] 首次导出失败，重新导航后重试...")
                await stock_page.goto(STOCK_REPORT_URL, timeout=60000)
                try:
                    await stock_page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(3)
                await self._click_query(stock_page)
                try:
                    await stock_page.wait_for_load_state("networkidle", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(3)
                await self._export_report(stock_page, download_dir, "库存报表", retry=0)
            return ok
        finally:
            await stock_page.close()
            safe_print("  [库存报表] 独立页签已关闭")

    # ── BOM循环查询 ──────────────────────────────────────

    async def _run_bom(self, page, context, download_dir, material_codes) -> bool:
        safe_print("\n" + "=" * 50)
        safe_print("BOM循环查询")
        safe_print("=" * 50)

        ok = await self.login_for_page(context, page, BOM_REPORT_URL)
        if not ok:
            safe_print("  [BOM] 登录失败，跳过")
            return False

        factory_code = self.config_manager.get_fanruan_config("factory_code", "664")
        username = self.config_manager.get_fanruan_config("username", "HSA697")
        password = self.secure_manager.load_password("fanruan") or self.config_manager.get_fanruan_config("password")

        factory_set = False
        success = 0
        fail = 0

        for idx, code in enumerate(material_codes, 1):
            safe_print(f"\n  [{idx}/{len(material_codes)}] {code}")
            try:
                async def process_one_code():
                    nonlocal factory_set
                    if not factory_set:
                        await self._select_factory(page, factory_code)
                        factory_set = True
                    await asyncio.sleep(0.3)

                    # 输入料号
                    input_ok = False
                    try:
                        el = page.locator('[widgetname="P_ITEMID"] input')
                        await el.wait_for(state="attached", timeout=8000)
                        await el.fill(code)
                        input_ok = True
                    except Exception:
                        pass
                    if not input_ok:
                        try:
                            await page.evaluate(f"_g().parameterEl.getWidgetByName('P_ITEMID').setValue({json.dumps(code)})")
                            input_ok = True
                        except Exception as e:
                            safe_print(f"  ! 输入料号失败: {e}")
                            return False

                    await self._click_query(page)
                    safe_print(f"  [等待] 导出料号{code}...")
                    return await self._export_report(page, download_dir, code)

                ok = await asyncio.wait_for(process_one_code(), timeout=300)
                if ok:
                    success += 1
                else:
                    fail += 1
            except asyncio.TimeoutError:
                safe_print(f"  ! 料号{code}处理超时(300s)，跳过")
                fail += 1
            except Exception as e:
                safe_print(f"  ! 料号{code}出错: {e}")
                fail += 1

        safe_print(f"\n  BOM完成: 成功{success}, 失败{fail}")
        return success > 0

    # ── 主执行 ──────────────────────────────────────────

    async def run_all(self, page, context) -> Dict[str, bool]:
        """执行所有帆软报表任务"""
        results = {}

        for task_id, label in self.TASKS:
            safe_print(f"\n{'=' * 50}")
            safe_print(f"  {label}")
            safe_print("=" * 50)

            try:
                if task_id == "bom":
                    material_codes = self._load_material_codes()
                    if not material_codes:
                        safe_print("  [跳过] BOM: 无物料编码")
                        results[task_id] = False
                        continue
                    d = self.config_manager.get_fanruan_config("dir_bom", "")
                    if not d:
                        d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads", "bom")
                    os.makedirs(d, exist_ok=True)
                    results[task_id] = await self._run_bom(page, context, d, material_codes)

                elif task_id == "report1":
                    d = self.config_manager.get_fanruan_config("dir_report1", "")
                    os.makedirs(d, exist_ok=True)
                    results[task_id] = await self._run_report1(page, context, d)

                elif task_id == "report2":
                    d = self.config_manager.get_fanruan_config("dir_report2", "")
                    os.makedirs(d, exist_ok=True)
                    results[task_id] = await self._run_report2(page, context, d)

                elif task_id == "stock":
                    d = self.config_manager.get_fanruan_config("dir_stock", "")
                    os.makedirs(d, exist_ok=True)
                    results[task_id] = await self._run_stock(page, context, d)

            except Exception as e:
                safe_print(f"\n[帆软] [FAIL] {label}: {e}")
                traceback.print_exc()
                results[task_id] = False

        return results


# ═══════════════════════════════════════════════════════
# 主执行器
# ═══════════════════════════════════════════════════════

class ReportDownloader:
    """报表下载主控制器 - 执行顺序：SCM → OA → 帆软"""

    def __init__(self):
        self.config_manager = ConfigManager()
        self.secure_manager = SecurePasswordManager(self.config_manager)
        self.scm = SCMSystem(self.config_manager, self.secure_manager)
        self.oa = OASystem(self.config_manager, self.secure_manager)
        self.fanruan = FanruanSystem(self.config_manager, self.secure_manager)

        # 日志（单文件 report_downloader.log，每次运行覆盖，仅保留最近一次）
        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "report_downloader.log")
        try:
            with open(self.log_file, "w", encoding="utf-8"):
                pass  # 清空旧日志，本次运行从头记录
        except Exception:
            pass

    def _log(self, message):
        """追加日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {message}\n")
        except Exception:
            pass

    async def run_all(self):
        """运行所有任务"""
        safe_print("\n" + "=" * 60)
        safe_print("  统一报表下载工具 V2.2 - 启动")
        safe_print("  执行顺序：SCM → OA → 帆软")
        safe_print("=" * 60)

        # 检查依赖
        deps = ["playwright", "pandas", "openpyxl", "ddddocr", "cryptography"]
        if not _check_deps(deps):
            return

        start_time = datetime.now()
        p, browser = None, None

        try:
            # 创建浏览器
            safe_print("\n[启动] 初始化浏览器...")
            p, browser, context, page = await create_browser()

            # ── Phase 1: SCM ──
            safe_print("\n" + "=" * 60)
            safe_print("  Phase 1: SCM 系统任务")
            safe_print("=" * 60)
            scm_results = await self.scm.run_all(page, context)
            scm_ok = sum(1 for v in scm_results.values() if v)
            scm_fail = sum(1 for v in scm_results.values() if not v)
            self._log(f"SCM: 成功{scm_ok}, 失败{scm_fail}")

            # ── Phase 2: OA ──
            safe_print("\n" + "=" * 60)
            safe_print("  Phase 2: OA 系统任务 - 生成计划.xlsx")
            safe_print("=" * 60)
            oa_ok = await self.oa.run(page)
            self._log(f"OA: {'成功' if oa_ok else '失败'}")

            # ── Phase 3: 帆软 ──
            safe_print("\n" + "=" * 60)
            safe_print("  Phase 3: 帆软报表任务")
            safe_print("=" * 60)
            fanruan_results = await self.fanruan.run_all(page, context)
            fanruan_ok = sum(1 for v in fanruan_results.values() if v)
            fanruan_fail = sum(1 for v in fanruan_results.values() if not v)
            self._log(f"帆软: 成功{fanruan_ok}, 失败{fanruan_fail}")

        except Exception as e:
            safe_print(f"\n[错误] 执行失败：{e}")
            traceback.print_exc()
            self._log(f"异常: {e}")

        finally:
            elapsed = datetime.now() - start_time
            total_sec = int(elapsed.total_seconds())
            self._log(f"全部完成，总用时：{total_sec // 60}分{total_sec % 60}秒")

            safe_print("\n" + "=" * 60)
            safe_print(f"  全部任务完成！总耗时：{total_sec // 60}分{total_sec % 60}秒")
            safe_print("=" * 60)

            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if p:
                try:
                    await p.stop()
                except Exception:
                    pass

    async def _run_module(self, module_name, run_func, label):
        """运行单个模块的通用方法"""
        safe_print("\n" + "=" * 60)
        safe_print(f"  {label}")
        safe_print("=" * 60)

        start_time = datetime.now()
        p, browser = None, None

        try:
            safe_print("\n[启动] 初始化浏览器...")
            p, browser, context, page = await create_browser()
            await run_func(page, context)
        except Exception as e:
            safe_print(f"\n[错误] 执行失败：{e}")
            traceback.print_exc()
            self._log(f"异常: {e}")
        finally:
            elapsed = datetime.now() - start_time
            total_sec = int(elapsed.total_seconds())
            self._log(f"{module_name}完成，总用时：{total_sec // 60}分{total_sec % 60}秒")
            safe_print("\n" + "=" * 60)
            safe_print(f"  {module_name}任务完成！总耗时：{total_sec // 60}分{total_sec % 60}秒")
            safe_print("=" * 60)
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if p:
                try:
                    await p.stop()
                except Exception:
                    pass

    async def run_scm_only(self):
        """只运行 SCM 模块"""
        async def _scm(page, context):
            scm_results = await self.scm.run_all(page, context)
            scm_ok = sum(1 for v in scm_results.values() if v)
            scm_fail = sum(1 for v in scm_results.values() if not v)
            self._log(f"SCM: 成功{scm_ok}, 失败{scm_fail}")
        await self._run_module("SCM", _scm, "SCM 系统任务（单独模式）")

    async def run_oa_only(self):
        """只运行 OA 模块"""
        async def _oa(page, context):
            oa_ok = await self.oa.run(page)
            self._log(f"OA: {'成功' if oa_ok else '失败'}")
        await self._run_module("OA", _oa, "OA 系统任务（单独模式）")

    async def run_fanruan_only(self):
        """只运行帆软模块"""
        async def _fanruan(page, context):
            fanruan_results = await self.fanruan.run_all(page, context)
            fanruan_ok = sum(1 for v in fanruan_results.values() if v)
            fanruan_fail = sum(1 for v in fanruan_results.values() if not v)
            self._log(f"帆软: 成功{fanruan_ok}, 失败{fanruan_fail}")
        await self._run_module("帆软", _fanruan, "帆软报表任务（单独模式）")


# ═══════════════════════════════════════════════════════
# 入口函数
# ═══════════════════════════════════════════════════════

import argparse

def _parse_args():
    parser = argparse.ArgumentParser(description="Whirlpool China 统一报表下载工具 V2.2")
    parser.add_argument("--module", choices=["scm", "oa", "fanruan"],
                        help="只运行指定模块（scm/oa/fanruan），默认全量运行")
    return parser.parse_args()

async def main(module=None):
    downloader = ReportDownloader()
    if module == "scm":
        await downloader.run_scm_only()
    elif module == "oa":
        await downloader.run_oa_only()
    elif module == "fanruan":
        await downloader.run_fanruan_only()
    else:
        await downloader.run_all()


if __name__ == "__main__":
    if not _check_deps(["playwright", "pandas", "openpyxl", "ddddocr", "cryptography", "lxml"]):
        sys.exit(1)
    args = _parse_args()
    asyncio.run(main(module=args.module))
