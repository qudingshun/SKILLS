# -*- coding: utf-8 -*-
"""
诊断：冷启动 applet 是否能最终渲染。把 ie2 置前台，轮询 6 分钟看 Forms 窗口
是否出现非桌面内容。
"""
import os, sys, time, win32gui
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import erp_ie11, erp_navigator, erp_forms, erp_ui
from erp_flow_org import ocr_hits, save_shot

RESP = "PO,SANYO合肥三洋物料计划员"
FUNC_ORG = "更改组织"

ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
assert ie and erp_ie11.is_logged_in(ie)
print("[OK] logged in")
erp_navigator.expand_responsibility(ie, RESP)
url = erp_navigator.read_function_url(ie, FUNC_ORG, resp_name=RESP)
before = erp_navigator.snapshot_forms_windows()
ie2 = erp_navigator.open_forms_window(url)
# 把承载 applet 的 ie2 窗口置前台，让 applet 有机会初始化
try:
    win32gui.SetForegroundWindow(int(ie2.HWND))
    print("[DIAG] ie2 已置前台 hwnd=", ie2.HWND)
except Exception as e:
    print("[DIAG] SetForegroundWindow ie2 失败:", e)
time.sleep(3.0)

hwnd, title = erp_navigator.wait_new_forms_window(before, timeout=300)
print("[OK] new forms hwnd=", hwnd, title)
app = erp_forms.FormsApp(); app.connect_by_hwnd(hwnd)

t0 = time.time()
last = ""
while time.time() - t0 < 360:
    erp_ui.focus_window(app, settle=1.0)
    img = erp_ui.capture(app, focus=True)
    hits = ocr_hits(img)
    # 桌面特征词；若出现非桌面词（组织/工厂/确定/MO/申请），说明 applet 渲染了
    desktop = {"输入你的PIN","合肥市","大部晴朗","查看完整预报","10月24日","10:","南非","植物园"}
    non_desktop = [t for t, s, r in hits if t.strip() not in desktop and len(t.strip()) > 1]
    line = " | ".join(non_desktop[:6])
    if line != last:
        print(f"[t={int(time.time()-t0)}s] tokens={len(hits)} non-desktop: {line}")
        last = line
    if any(k in line for k in ("组织", "工厂", "确定", "MO", "申请", "版本")):
        print("[BREAK] 检测到 applet 内容，停止等待")
        break
    time.sleep(20.0)
img = erp_ui.capture(app, focus=True)
save_shot(img, r"E:\SKILLS\WHP-whirlpool-erp\logs\diag_wait_end.png")
print("MEDIA:E:\\SKILLS\\WHP-whirlpool-erp\\logs\\diag_wait_end.png")
print("[DIAG] 等待结束，耗时", int(time.time()-t0), "s")
