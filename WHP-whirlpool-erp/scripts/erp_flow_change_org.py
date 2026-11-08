# -*- coding: utf-8 -*-
"""
「更改组织」流程 —— PO,SANYO合肥三洋物料计划员 职责下进入 ERP 并切换组织。

流程（全程不碰默认浏览器；IE 窗口全保留，退出用 erp_ops.py logout）：
  1) 复用已登录的 EBS 主页 IE（不重复开浏览器）
  2) 展开「PO,SANYO合肥三洋物料计划员」职责
  3) 只读取得「更改组织」的 launchForm URL（不点击网页链接）
  4) 自开 IE 窗口加载该 URL（applet 一定跑在 IE11 Java 插件里）
  5) 等新 Forms 窗口出现（与启动前快照做差集，避免误抓已有工作台窗口）
  6) OCR 探测界面；出现工厂列表则点选「洗衣机三工厂」→「确定」
  7) 复核截图 logs/org_change_verify.png

用法:
  python scripts/erp_flow_change_org.py                 # 全流程 + 选择洗衣机三工厂
  python scripts/erp_flow_change_org.py <工厂名>          # 选择指定工厂
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import erp_ie11
import erp_navigator
import erp_forms
import erp_ui
from erp_flow_org import ocr_hits, find_row, save_shot

RESP = "PO,SANYO合肥三洋物料计划员"
FUNC = "更改组织"
DEFAULT_FACTORY = "洗衣机三工厂"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def wait_new_forms_window(before, timeout=150):
    """轮询新出现的 Forms 窗口（不在 before 快照中的 hwnd）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(4)
        snap = erp_navigator.snapshot_forms_windows()
        for hwnd, title in snap.items():
            if hwnd not in before:
                return hwnd, title
    return None, None


def main():
    factory = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FACTORY

    # ① 复用/新建登录会话（open_and_login 自带复用与清理逻辑）
    ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
    if ie is None or not erp_ie11.is_logged_in(ie):
        print("[FAIL] EBS 登录失败")
        sys.exit(2)

    before = erp_navigator.snapshot_forms_windows()
    print(f"[导航] 启动前已有 Forms 窗口 {len(before)} 个")

    # ② 职责展开 + ③ 读「更改组织」URL
    if not erp_navigator.expand_responsibility(ie, RESP):
        print(f"[FAIL] 职责「{RESP}」展开失败")
        sys.exit(3)
    url = erp_navigator.read_function_url(ie, FUNC, resp_name=RESP)
    if not url:
        print(f"[FAIL] 职责「{RESP}」下未找到功能「{FUNC}」")
        import erp_navigator as _n
        for f in _n.list_functions(ie, resp_name=RESP):
            print(f"      可用功能: {f['name']}")
        sys.exit(3)
    print(f"[OK] 「{FUNC}」URL: {url[:100]}...")

    # ④ 自开 IE 窗口加载
    ie2 = erp_navigator.open_forms_window(url)
    if ie2 is None:
        print("[FAIL] 承载 IE 窗口创建失败")
        sys.exit(4)

    # ⑤ 等新 Forms 窗口
    hwnd, title = wait_new_forms_window(before)
    if hwnd is None:
        print("[FAIL] 等待 150s 未出现新 Forms 窗口"
              "（可能同一 JRE 第二个 applet 起不来；或提示窗口被误判）")
        shot = os.path.join(PROJECT_DIR, "logs", "org_change_stuck.png")
        try:
            erp_ie11.screenshot_ie(ie2, shot)
            print(f"MEDIA:{shot}")
        except Exception:
            pass
        sys.exit(4)
    print(f"[OK] 新 Forms 窗口 hwnd={hwnd} title={title!r}")

    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(hwnd):
        print("[FAIL] 连接 Forms 窗口失败")
        sys.exit(4)

    # ⑥ OCR 探测 + 选择
    img = erp_ui.capture(app, focus=True)
    hits = ocr_hits(img)
    keys = ("洗衣机", "电机", "程控器", "组织", "确定", "查找", "取消", "MO")
    print(f"[OCR] 探测到 {len(hits)} 处文本：")
    for t, s, r in hits:
        if any(k in t for k in keys):
            print(f"   {t!r} score={s:.2f} center={r.center}")

    probe_shot = os.path.join(PROJECT_DIR, "logs", "org_change_probe.png")
    save_shot(img, probe_shot)

    row = find_row(hits, factory)
    if row is None:
        print(f"[WARN] 当前界面未见工厂行「{factory}」"
              f"（可能组织列表 LOV 尚未弹出，或需先点 组织 字段）")
        print(f"MEDIA:{probe_shot}")
        sys.exit(6)

    print(f"[OK] 定位行「{factory}」center={row.center} score={row.score:.2f}")
    if not erp_ui.click_rect(app, row, dx=0.5, dy=0.5):
        sys.exit(6)
    time.sleep(0.8)

    img2 = erp_ui.capture(app, focus=False)
    ok_btn = find_row(ocr_hits(img2), "确定")
    if ok_btn is None:
        print("[FAIL] 未找到「确定」按钮，中止")
        sys.exit(6)
    if not erp_ui.click_rect(app, ok_btn, dx=0.5, dy=0.5):
        sys.exit(6)
    time.sleep(2.0)

    # ⑦ 复核
    img3 = erp_ui.capture(app, focus=False)
    if find_row(ocr_hits(img3), "确定") is None:
        print("[OK] 复核：「确定」已消失（组织 LOV 已提交）")
    else:
        print("[WARN] 复核：界面仍有「确定」，请人工确认")
    verify_shot = os.path.join(PROJECT_DIR, "logs", "org_change_verify.png")
    if save_shot(img3, verify_shot):
        print(f"[OK] 复核截图: {verify_shot}")
        print(f"MEDIA:{verify_shot}")
    print("[提示] ERP 已按你的要求保持打开；结束时运行 erp_ops.py logout")


if __name__ == "__main__":
    main()
