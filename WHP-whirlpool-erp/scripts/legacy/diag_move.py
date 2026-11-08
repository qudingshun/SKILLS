# -*- coding: utf-8 -*-
"""
诊断：冷启动后 Forms 窗口离屏(-32000,-32000)，验证 SetWindowPos 移到屏幕内后
applet 是否会渲染出 LOV 内容。
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import win32gui, win32con
import erp_ie11, erp_navigator, erp_forms, erp_ui
from erp_flow_org import ocr_hits, save_shot

RESP = "PO,SANYO合肥三洋物料计划员"
FUNC_ORG = "更改组织"

ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
assert ie and erp_ie11.is_logged_in(ie), "login failed"
print("[OK] logged in")

if not erp_navigator.expand_responsibility(ie, RESP):
    print("[FAIL] expand resp"); sys.exit(3)
url = erp_navigator.read_function_url(ie, FUNC_ORG, resp_name=RESP)
print("[OK] url", url[:80])
before = erp_navigator.snapshot_forms_windows()
ie2 = erp_navigator.open_forms_window(url)
hwnd, title = erp_navigator.wait_new_forms_window(before)
print("[OK] new forms hwnd=", hwnd, title)
app = erp_forms.FormsApp()
app.connect_by_hwnd(hwnd)

# 读窗口矩形
r = erp_ui.window_rect(app)
print("[DIAG] window rect before move:", r)

# 移到屏幕内并显示
if r:
    l, t, rr, b = r
    w, h = rr - l, b - t
    if l < 0 or t < 0 or w <= 0 or h <= 0:
        w, h = max(400, w), max(300, h)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, 100, 100, w, h,
                              win32con.SWP_SHOWWINDOW)
        print("[DIAG] moved window to (100,100) size", (w, h))
        time.sleep(3.0)

# 置前 + 截图
erp_ui.focus_window(app, settle=2.0)
img = erp_ui.capture(app, focus=True)
r2 = erp_ui.window_rect(app)
print("[DIAG] window rect after:", r2, "capture size:", None if img is None else img.size)
hits = ocr_hits(img)
print("[DIAG] OCR tokens:", len(hits))
for t, s, rr in sorted(hits, key=lambda x:(x[2].y, x[2].x))[:40]:
    print(f"   {t!r} score={s:.2f} center={rr.center}")
save_shot(img, r"E:\SKILLS\WHP-whirlpool-erp\logs\diag_move.png")
print("MEDIA:E:\\SKILLS\\WHP-whirlpool-erp\\logs\\diag_move.png")
