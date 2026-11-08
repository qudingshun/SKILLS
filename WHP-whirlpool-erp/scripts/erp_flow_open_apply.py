# -*- coding: utf-8 -*-
"""
打开「常用表单 → 申请」流程。

在现有 Forms 会话（浏览器/导航窗）里：
  1) 找最新 Forms 窗口并连接
  2) OCR 定位「常用表单」列表里**精确等于**「申请」的条目
     （注意区分「申请汇总」——必须整词相等，别误点）
  3) 点选它 → 点「打开(O)」
  4) 复核截图 logs/apply_open_verify.png

用法: python scripts/erp_flow_open_apply.py [表单名]   # 默认 申请
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import erp_navigator
import erp_forms
import erp_ui
from erp_flow_org import ocr_hits, save_shot

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(PROJECT_DIR, "logs", "apply_open_verify.png")
PROBE = os.path.join(PROJECT_DIR, "logs", "apply_open_probe.png")


def pick_exact(hits, word):
    """整词相等的命中（去掉前后缀'1.'/'2.'等），多个时取 y 最大（靠下的）"""
    cands = []
    for t, s, r in hits:
        clean = t.strip().lstrip("0123456789.、.  ")
        if clean == word:
            cands.append((r, s))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0].y)
    return cands[-1][0]


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else "申请"

    snap = erp_navigator.snapshot_forms_windows()
    if not snap:
        print("[FAIL] 当前没有任何 Forms 窗口；先跑 erp_flow_change_org.py")
        sys.exit(4)
    hwnd, title = list(snap.items())[-1]
    print(f"[OK] 连接 Forms 窗口 hwnd={hwnd} title={title!r}")
    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(int(hwnd)):
        sys.exit(4)

    img = erp_ui.capture(app, focus=True)
    hits = ocr_hits(img)
    save_shot(img, PROBE)

    # 可见性检查
    print("[OCR] 界面文本：")
    for t, s, r in hits:
        clean = t.strip().lstrip("0123456789.、.  ")
        if any(k in clean for k in ("常用表单", "申请", "打开", "功能")):
            print(f"   {t!r} score={s:.2f} center={r.center}")

    item = pick_exact(hits, word)
    if item is None:
        print(f"[FAIL] 列表里没有整词命中「{word}」（可能有「申请汇总」等近似项）")
        print(f"MEDIA:{PROBE}")
        sys.exit(6)
    print(f"[OK] 「{word}」条目 center={item.center} rel=({item.x},{item.y},"
          f"{item.w},{item.h}) score={item.score:.2f}")

    if not erp_ui.click_rect(app, item, dx=0.5, dy=0.5):
        sys.exit(6)
    time.sleep(0.8)

    # 点「打开(O)」
    img2 = erp_ui.capture(app, focus=False)
    btn = None
    for t, s, r in ocr_hits(img2):
        clean = t.strip().lstrip("0123456789.( ")
        if clean.startswith("打开"):
            btn = r
            break
    if btn is None:
        print("[FAIL] 未找到「打开(O)」按钮")
        sys.exit(6)
    print(f"[OK] 「打开(O)」center={btn.center} score={btn.score:.2f}")
    if not erp_ui.click_rect(app, btn, dx=0.5, dy=0.5):
        sys.exit(6)

    # 等新窗口/新界面弹出
    time.sleep(5)
    img3 = erp_ui.capture(app, focus=True)
    time.sleep(1)
    if save_shot(img3, VERIFY):
        print(f"[OK] 打开后截图: {VERIFY}")
        texts = [t for t, *_ in ocr_hits(img3)]
        summary = " | ".join(x for x in texts if x.strip())[:400]
        print(f"[OCR] 打开后界面文本: {summary}")
        print(f"MEDIA:{VERIFY}")


if __name__ == "__main__":
    main()
