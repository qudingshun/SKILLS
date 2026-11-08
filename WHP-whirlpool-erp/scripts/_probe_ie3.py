# -*- coding: utf-8 -*-
"""临时探针：登录后打开「更改组织」RF.jsp，看 Java 表单能否在 IE 内核里起来。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ui                      # 必须在取窗口坐标前导入：开 DPI 感知
import erp_ie
import win32gui
from PIL import ImageGrab
from pywinauto import keyboard, mouse
from erp_common import ERP_USERNAME, get_erp_password
from erp_flow_org import ocr_hits

LOGS = erp_ie.LOGS
RF = (erp_ie.ERP_BASE + "/OA_HTML/RF.jsp?function_id=261&resp_id=51318"
      "&resp_appl_id=201&security_group_id=0&lang_code=ZHS")


def shot(h):
    win32gui.ShowWindow(h, 3)
    try:
        win32gui.SetForegroundWindow(h)
    except Exception:
        pass
    time.sleep(0.6)
    l, t, r, b = win32gui.GetWindowRect(h)
    return ImageGrab.grab(bbox=(l, t, r, b), all_screens=True), (l, t)


def click(h, org, x, y, settle=0.5):
    win32gui.SetForegroundWindow(h)
    time.sleep(0.3)
    mouse.click(button="left", coords=(org[0] + x, org[1] + y))
    time.sleep(settle)


def alive(h):
    try:
        return bool(win32gui.IsWindow(h))
    except Exception:
        return False


def login(h):
    img, org = shot(h)
    toks = list(ocr_hits(img))
    u = next((r for tx, s, r in toks if "用户" in tx), None)
    if not u:
        print("  找不到用户名标签，已是登录态？", flush=True)
        return False
    click(h, org, u.x + u.w + 180, u.y + u.h // 2)
    keyboard.send_keys(ERP_USERNAME, with_spaces=True)
    time.sleep(0.5)
    keyboard.send_keys("{TAB}")
    time.sleep(0.5)
    keyboard.send_keys(get_erp_password(), with_spaces=True)
    time.sleep(0.8)
    keyboard.send_keys("{ENTER}")
    print("  已提交登录", flush=True)
    return True


def page_text(h):
    img, _org = shot(h)
    t = " | ".join(tx for tx, s, r in ocr_hits(img))
    img.save(os.path.join(LOGS, "ie_last.png"))
    return t


if __name__ == "__main__":
    erp_ie.kill_hosts()
    h = erp_ie.open_host()
    erp_ie.wait_page(lambda r, u, t: r == "Complete", timeout=90, note="登录页")
    time.sleep(2)

    if login(h):
        for i in range(12):
            time.sleep(2)
            if not alive(h):
                print("!! 宿主窗口没了", flush=True)
                break
            t = page_text(h)
            print(f"[登录 {i * 2}s] {t[:120]}", flush=True)
            if "登录身份" in t or "主页" in t:
                print("=== 登录成功 ===", flush=True)
                break

    # 打开「更改组织」
    print("→ 打开 RF.jsp（更改组织）", flush=True)
    erp_ie.navigate(RF)
    for i in range(30):
        time.sleep(3)
        if not alive(h):
            print("!! 宿主窗口没了", flush=True)
            break
        t = page_text(h)
        st = erp_ie.status()
        print(f"[表单 {i * 3}s] {st[2]} :: {t[:200]}", flush=True)
        if "更改组织" in t or "常用表单" in t:
            print("=== 表单已就绪 ===", flush=True)
            break
