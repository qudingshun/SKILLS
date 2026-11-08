# -*- coding: utf-8 -*-
"""
点掉 Forms 里的模态提示弹窗（如「注意：组织和地点不允许为空！」）。

用法:
  python scripts/erp_flow_dismiss_dialog.py 确定     # 点弹窗上的按钮（默认 确定）
  python scripts/erp_flow_dismiss_dialog.py 取消
限定规则：只在弹窗区域（有「注意」/「提示」/「警告」标志时优先弹窗附近）找按钮，
避免误点表单底部同名词按钮。复核截图 logs/dialog_dismiss_verify.png
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
VERIFY = os.path.join(PROJECT_DIR, "logs", "dialog_dismiss_verify.png")

# 「注意/提示/警告」标题图标常出现在弹窗标题行；把搜索范围收紧到弹窗窗口
DIALOG_TITLE_KEYS = ("注意", "提示", "警告", "确认", "询问")


def find_dialog_bounds(hits):
    ys = [r.y for t, s, r in hits
          if any(k in t.strip() for k in DIALOG_TITLE_KEYS)]
    if not ys:
        return None
    top = min(ys)
    # 弹窗一般 ~250px 高；以此为搜索带
    return top - 10, top + 300


def main():
    word = sys.argv[1] if len(sys.argv) > 1 else "确定"

    snap = erp_navigator.snapshot_forms_windows()
    if not snap:
        print("[FAIL] 没有 Forms 窗口")
        sys.exit(4)
    hwnd, title = list(snap.items())[-1]
    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(int(hwnd)):
        sys.exit(4)
    print(f"[OK] 已连接 Forms 窗口 hwnd={hwnd}")

    img = erp_ui.capture(app, focus=True)
    hits = ocr_hits(img)
    band = find_dialog_bounds(hits)
    if band:
        top, bottom = band
        print(f"[OK] 检测到弹窗（y≈{top}~{bottom}），按钮只在弹窗内找")
        cands = [(t, s, r) for t, s, r in hits
                 if top - 20 <= r.y <= bottom and word in t.strip()]
        if not cands:
            # 兜底：放宽整条弹窗带
            cands = [(t, s, r) for t, s, r in hits
                     if top - 20 <= r.y <= bottom + 40 and word in t.strip()]
    else:
        print("[WARN] 未检出「注意/提示/警告」标题，退化到全图找按钮"
              "（只有唯一命中才执行）")
        cands = [(t, s, r) for t, s, r in hits if word in t.strip()]
        if len(cands) != 1:
            print(f"[FAIL] 全图「{word}」命中 {len(cands)} 处，不唯一，取消操作")
            for t, s, r in cands:
                print(f"   {t!r} center={r.center}")
            sys.exit(6)

    if not cands:
        print(f"[FAIL] 弹窗内没找到「{word}」按钮")
        sys.exit(6)
    cands.sort(key=lambda x: x[2].center[0])   # 弹窗内取最靠左（确定在取消左边）
    t, s, r = cands[0]
    print(f"[OK] 「{t}」center={r.center} rel=({r.x},{r.y},{r.w},{r.h}) "
          f"score={s:.2f}")
    if not erp_ui.click_rect(app, r, dx=0.5, dy=0.5):
        sys.exit(6)
    time.sleep(1.5)

    img2 = erp_ui.capture(app, focus=False)
    gone = find_dialog_bounds(ocr_hits(img2)) is None
    if gone:
        print("[OK] 复核：弹窗已消失")
    else:
        print("[WARN] 复核：弹窗（注意/提示标题）仍在，可能还有下一层提示")
    if save_shot(img2, VERIFY):
        texts = [x for x, *_ in ocr_hits(img2) if x.strip()]
        print("[OCR] 当前界面文本: "
              + " | ".join(texts)[:400])
        print(f"MEDIA:{VERIFY}")


if __name__ == "__main__":
    main()
