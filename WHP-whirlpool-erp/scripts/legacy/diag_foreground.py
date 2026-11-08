# -*- coding: utf-8 -*-
"""
诊断：AttachThreadInput + SetForegroundWindow 强制置前 ie2 和 Forms 窗口，
验证冷启动 applet 是否能渲染出 LOV 内容。
"""
import os, sys, time, win32gui, win32process, win32api
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ie11, erp_navigator, erp_forms, erp_ui
from erp_flow_org import ocr_hits, save_shot

RESP = "PO,SANYO合肥三洋物料计划员"
FUNC_ORG = "更改组织"

def force_foreground(hwnd):
    hwnd = int(hwnd)
    if not win32gui.IsWindow(hwnd):
        return False
    try:
        my_tid = win32api.GetCurrentThreadId()
        tgt_tid, _ = win32process.GetWindowThreadProcessId(hwnd)
        if tgt_tid and tgt_tid != my_tid:
            win32api.AttachThreadInput(my_tid, tgt_tid, True)
        win32gui.SetForegroundWindow(hwnd)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        try:
            win32api.AttachThreadInput(my_tid, tgt_tid, False)
        except Exception:
            pass
        return True
    except Exception as e:
        print("[DIAG] force_foreground 失败:", e)
        return False

ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
assert ie and erp_ie11.is_logged_in(ie)
print("[OK] logged in")
erp_navigator.expand_responsibility(ie, RESP)
url = erp_navigator.read_function_url(ie, FUNC_ORG, resp_name=RESP)
print("[OK] url", url[:80])
before = erp_navigator.snapshot_forms_windows()
ie2 = erp_navigator.open_forms_window(url)
print("[DIAG] force_foreground ie2:", force_foreground(ie2.HWND))
time.sleep(3.0)
hwnd, title = erp_navigator.wait_new_forms_window(before, timeout=120)
print("[OK] new forms hwnd=", hwnd, title)
print("[DIAG] force_foreground forms:", force_foreground(hwnd))
time.sleep(3.0)
app = erp_forms.FormsApp(); app.connect_by_hwnd(hwnd)
erp_ui.focus_window(app, settle=2.0)
img = erp_ui.capture(app, focus=True)
hits = ocr_hits(img)
print("[DIAG] OCR tokens:", len(hits))
for t, s, r in sorted(hits, key=lambda x:(x[2].y, x[2].x))[:40]:
    print(f"   {t!r} score={s:.2f} center={r.center}")
save_shot(img, r"E:\SKILLS\WHP-whirlpool-erp\logs\diag_foreground.png")
print("MEDIA:E:\\SKILLS\\WHP-whirlpool-erp\\logs\\diag_foreground.png")
