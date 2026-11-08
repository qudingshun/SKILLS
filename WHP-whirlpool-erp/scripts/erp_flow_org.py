# -*- coding: utf-8 -*-
"""
组织（工厂）LOV 选择流程 —— MRP计划员工作台 第一步。

用法（workdir 或绝对路径均可，用 .venv 解释器跑）:
  python scripts/erp_flow_org.py probe             # 只探测，列出工厂行坐标
  python scripts/erp_flow_org.py select 洗衣机三工厂  # OCR 定位该行 → 点选 → 确定 → 复核

流程：
  1) 连接现有 Forms 窗口（reuse；新开请用 erp_ops.py open-forms --keep-ie）
  2) 置前 + 截图 + OCR 全图
  3) 找到含目标工厂名的行 → 行中心点击选中
  4) 点「确定」
  5) 复核截图（确认 LOV 关闭、组织已带入）
产物: logs/org_select_verify.png，最后一行 MEDIA:<绝对路径>
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import erp_forms
import erp_ui

VERIFY_SHOT = os.path.normpath(os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "logs", "org_select_verify.png"))


def connect_forms():
    app = erp_forms.FormsApp()
    if not app.connect(title_re="Oracle Applications.*ERP.*", timeout=20):
        print("[FAIL] 未找到 Forms 窗口；先运行 "
              "erp_ops.py open-forms <职责> <功能> --keep-ie")
        sys.exit(1)
    return app


def ocr_hits(img):
    """[(text, score, rect)] ，rect 为 erp_ui.Rect"""
    import numpy as np  # noqa: F401  （erp_ui 内部依赖已随包导入）
    out = []
    for text, score, (x, y, w, h) in erp_ui.ocr_text(img):
        r = erp_ui.Rect(int(x), int(y), int(w), int(h), score=score,
                        name=text or "")
        out.append((text or "", score, r))
    return out


def find_row(hits, name):
    """找包含目标名的行文字；返回 Rect 或 None"""
    for text, _, r in hits:
        if name.replace(" ", "") in text.replace(" ", ""):
            return r
    return None


def save_shot(img, path):
    """PIL 直存（绕开 cv2 中文路径问题），路径的父目录必须已存在"""
    try:
        img.save(path)
        return True
    except Exception as e:
        print(f"[WARN] 截图保存失败: {e}")
        return False


def do_probe(app):
    img = erp_ui.capture(app, focus=True)
    hits = ocr_hits(img)
    keys = ("洗衣机", "工厂", "电机", "程控器", "MO", "确定", "查找", "取消")
    print(f"[OCR] 全图命中 {len(hits)} 处，相关行：")
    for t, s, r in hits:
        if any(k in t for k in keys):
            print(f"  {t!r} score={s:.2f} center={r.center} "
                  f"rel=({r.x},{r.y},{r.w},{r.h})")


def do_select(app, name):
    # ① 截图 + OCR
    img = erp_ui.capture(app, focus=True)
    hits = ocr_hits(img)
    row = find_row(hits, name)
    if row is None:
        print(f"[FAIL] OCR 未找到行「{name}」。请先 probe 看列表内容，"
              f"或该行不在可见区（LOV 可能需要滚动）")
        sys.exit(6)
    print(f"[OK] 定位行「{name}」center={row.center} "
          f"rel=({row.x},{row.y},{row.w},{row.h}) score={row.score:.2f}")

    # ② 点选该行（行中心）
    if not erp_ui.click_rect(app, row, dx=0.5, dy=0.5):
        sys.exit(6)
    time.sleep(0.8)

    # ③ 点「确定」
    img2 = erp_ui.capture(app, focus=False)
    ok_btn = find_row(ocr_hits(img2), "确定")
    if ok_btn is None:
        print("[FAIL] 未找到「确定」按钮，中止（未点击）")
        sys.exit(6)
    print(f"[OK] 定位「确定」center={ok_btn.center} score={ok_btn.score:.2f}")
    if not erp_ui.click_rect(app, ok_btn, dx=0.5, dy=0.5):
        sys.exit(6)
    time.sleep(2.0)

    # ④ 复核：LOV 应已关闭（图上不应再出现成串的工厂行 + 确定）
    img3 = erp_ui.capture(app, focus=False)
    hits3 = ocr_hits(img3)
    still = find_row(hits3, "确定")
    if still is None:
        print("[OK] 复核：「确定」已消失（LOV 已关闭，组织应已带入）")
    else:
        print(f"[WARN] 复核：图上仍可见「确定」，请人工确认是否选择成功")
    if save_shot(img3, VERIFY_SHOT):
        print(f"[OK] 复核截图: {VERIFY_SHOT}")
        print(f"MEDIA:{VERIFY_SHOT}")
    else:
        print("[WARN] 复核截图保存失败")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    app = connect_forms()
    if args[0] == "probe":
        do_probe(app)
    elif args[0] == "select":
        if len(args) < 2:
            print("[FAIL] 用法: select <工厂名，如 洗衣机三工厂>")
            sys.exit(1)
        do_select(app, args[1])
    else:
        print(f"[FAIL] 未知动作: {args[0]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
