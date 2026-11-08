# -*- coding: utf-8 -*-
"""
表头「说明」补填 + 保存 + 读回申请编号（微修脚本）。
前置状态：其余字段已全部就位（物料/数量/价格/日期/组织/地点/子库存）。
坐标体系：当前窗口最大化 2560x1600，capture 与点击同坐标系（物理像素）。
"""
import os
import sys
import time

sys.path.insert(0, r"E:\SKILLS\WHP-whirlpool-erp\scripts")

import erp_navigator
import erp_forms
import erp_ui
from erp_flow_org import ocr_hits, save_shot
from erp_ui import Rect

PROJECT_DIR = r"E:\SKILLS\WHP-whirlpool-erp"
VERIFY = os.path.join(PROJECT_DIR, "logs", "req_final.png")
DESC_S = "零头补录入库"


def ocr_now(app):
    img = erp_ui.capture(app, focus=False)
    hits = ocr_hits(img)
    if not hits:
        time.sleep(0.6)
        img = erp_ui.capture(app, focus=False)
        hits = ocr_hits(img)
    return img, hits


def main():
    snap = erp_navigator.snapshot_forms_windows()
    hwnd = list(snap.keys())[-1]
    app = erp_forms.FormsApp()
    app.connect_by_hwnd(int(hwnd))
    print(f"[OK] hwnd={hwnd} rect={erp_ui.window_rect(app)}")
    erp_ui.focus_window(app, settle=0.6)
    img, hits = ocr_now(app)

    # 表头说明标签（y<330 的精确「说明」）
    lab = None
    for t, s, r in hits:
        if t.strip() == "说明" and r.y < 330:
            lab = r
            break
    if lab is None:
        print("[FAIL] 表头说明标签未找到，中止")
        sys.exit(6)
    print(f"[OK] 说明标签 ({lab.x},{lab.y},{lab.w},{lab.h})")

    typed = False
    for dy in (0, -6, +6, -12, +12):
        bx = lab.x + lab.w + 60          # 框内安全点（框起点≈label右+10）
        by = lab.y + lab.h // 2 + dy
        erp_ui.click_rect(app, Rect(bx, by, 60, 24, name="说明框"),
                          dx=0.5, dy=0.5)
        time.sleep(0.35)
        app.window.type_keys("{END}", pause=0.02)
        app.window.type_keys("{BACKSPACE 40}", pause=0.02)
        app.window.type_keys(DESC_S, with_spaces=True, pause=0.03)
        time.sleep(0.9)
        _, hits = ocr_now(app)
        got = [t for t, s, r in hits
               if "补录入库" in t and 150 <= r.x <= 520 and 170 <= r.y <= 260]
        if got:
            print(f"[OK] 说明 → {got[0]!r}")
            typed = True
            break
        print(f"[RETRY] dy={dy} 未确认")
    if not typed:
        print("[FAIL] 说明未填上 —— 不保存，出图人工判断")
        img, _ = ocr_now(app)
        save_shot(img, VERIFY)
        print(f"MEDIA:{VERIFY}")
        sys.exit(7)

    # ── 保存 ──
    erp_ui.focus_window(app, settle=0.4)
    app.window.type_keys("^s")
    time.sleep(3.0)
    n = 0
    while n < 8:
        _, hits = ocr_now(app)
        cands = [(t, r) for t, s, r in hits
                 if ("确定" in t or t.strip() in ("是(Y)", "是"))
                 and (any(k in t2 for t2, _, _ in hits
                          for k in ("注意", "提示", "警告", "确认", "询问",
                                    "保存", "关闭")))]
        if not cands:
            break
        cands.sort(key=lambda x: x[1].center[0])
        t, r = cands[0]
        print(f"[弹窗] 点「{t}」{r.center}")
        erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
        time.sleep(1.4)
        n += 1
    print(f"[OK] 保存后清掉 {n} 个弹窗")

    img, hits = ocr_now(app)
    number = None
    for t, s, r in hits:
        clean = t.strip().replace(" ", "")
        if clean.isdigit() and len(clean) >= 8 and r.y < 330:
            number = clean
            break
    print(f"[{'SAVED' if number else 'CHECK'}] "
          f"{'申请编号=' + number if number else '未读到自动编号，请复核截图'}")
    save_shot(img, VERIFY)
    texts = [t for t, *_ in ocr_now(app)[1] if t.strip()]
    print("[OCR] 最终: " + " | ".join(texts)[:600])
    print(f"MEDIA:{VERIFY}")


if __name__ == "__main__":
    main()
