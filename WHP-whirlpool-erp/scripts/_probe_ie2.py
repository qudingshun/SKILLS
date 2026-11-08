# -*- coding: utf-8 -*-
"""临时探针：IE 内核宿主里用模拟点击完成登录，然后打开「更改组织」RF.jsp。"""
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
    win32gui.ShowWindow(h, 3)          # SW_MAXIMIZE
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


if __name__ == "__main__":
    erp_ie.kill_hosts()
    h = erp_ie.open_host()
    erp_ie.wait_page(lambda r, u, t: r == "Complete", timeout=90, note="登录页")
    time.sleep(2)

    img, org = shot(h)
    img.save(os.path.join(LOGS, "ie_step1.png"))
    toks = list(ocr_hits(img))
    print("origin", org, "img", img.size, flush=True)
    for tx, s, r in toks:
        print("   ", round(s, 2), repr(tx), (r.x, r.y, r.w, r.h), flush=True)

    u = next((r for tx, s, r in toks if "用户" in tx), None)
    print("用户名锚点", u, flush=True)
    if not u:
        sys.exit("定位失败")

    # 口令框不用 OCR 找（「*口令」常被识成别的字），直接按 Tab 走 DOM 顺序
    click(h, org, u.x + u.w + 180, u.y + u.h // 2)
    keyboard.send_keys(ERP_USERNAME, with_spaces=True)
    time.sleep(0.4)
    keyboard.send_keys("{TAB}")
    time.sleep(0.4)
    keyboard.send_keys(get_erp_password(), with_spaces=True)
    time.sleep(0.6)
    img, org = shot(h)
    img.save(os.path.join(LOGS, "ie_step2_typed.png"))
    print("已输入，回车提交", flush=True)
    keyboard.send_keys("{ENTER}")
    time.sleep(1.2)

    for i in range(15):
        time.sleep(3)
        img, org = shot(h)
        txt = " | ".join(tx for tx, s, r in ocr_hits(img))
        st = erp_ie.status()
        print(f"[{(i + 1) * 3}s] {st[0]} {st[2]} :: {txt[:200]}", flush=True)
        img.save(os.path.join(LOGS, f"ie_step3_{i}.png"))
        if "更改组织" in txt or "常用表单" in txt:
            print("=== 进了表单 ===", flush=True)
            break
