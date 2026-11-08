# -*- coding: utf-8 -*-
"""临时探针：在 IE 内核宿主窗口里模拟点击完成 EBS 登录。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win32gui
from PIL import ImageGrab
from pywinauto import keyboard, mouse
from erp_common import ERP_USERNAME, get_erp_password
from erp_flow_org import ocr_hits

LOGS = r"E:\SKILLS\WHP-whirlpool-erp\logs"


def find_host():
    out = []

    def cb(h, _):
        if win32gui.GetWindowText(h) == "EBS-IE" and win32gui.IsWindowVisible(h):
            out.append(h)
    win32gui.EnumWindows(cb, None)
    return out[0] if out else None


def shot(h):
    l, t, r, b = win32gui.GetWindowRect(h)
    return ImageGrab.grab(bbox=(l, t, r, b), all_screens=True), (l, t)


def click(h, origin, x, y, settle=0.4):
    win32gui.SetForegroundWindow(h)
    time.sleep(0.3)
    mouse.click(button="left", coords=(origin[0] + x, origin[1] + y))
    time.sleep(settle)


if __name__ == "__main__":
    h = find_host()
    print("host", h, win32gui.GetWindowRect(h), flush=True)
    img, org = shot(h)
    toks = list(ocr_hits(img))
    for tx, s, r in toks:
        print("  ", round(s, 2), repr(tx), (r.x, r.y, r.w, r.h), flush=True)

    u = next((r for tx, s, r in toks if "用户名" in tx), None)
    p = next((r for tx, s, r in toks if "口令" in tx), None)
    btn = next((r for tx, s, r in toks if tx.strip() == "登录"), None)
    print("labels", u, p, btn, flush=True)
    if not (u and p and btn):
        sys.exit("定位失败")

    click(h, org, u.x + u.w + 180, u.y + u.h // 2)
    keyboard.send_keys(ERP_USERNAME, with_spaces=True)
    time.sleep(0.5)
    click(h, org, p.x + p.w + 180, p.y + p.h // 2)
    keyboard.send_keys(get_erp_password(), with_spaces=True)
    time.sleep(0.5)
    print("typed, clicking 登录", flush=True)
    click(h, org, btn.x + btn.w // 2, btn.y + btn.h // 2, settle=1.0)

    for i in range(12):
        time.sleep(4)
        img, org = shot(h)
        txt = " | ".join(tx for tx, s, r in ocr_hits(img))
        print(f"[{(i + 1) * 4}s] {txt[:260]}", flush=True)
        img.save(os.path.join(LOGS, f"ie_login_{i}.png"))
        if "更改组织" in txt or "常用表单" in txt or "职责" in txt:
            print("=== 进主页/表单了 ===", flush=True)
            break
