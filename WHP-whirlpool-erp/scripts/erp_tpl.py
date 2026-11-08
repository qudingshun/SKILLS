#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_tpl - Oracle Forms 界面模板库管理工具

用途：把"界面元素"变成可复用的**图像模板**，从而在不同分辨率/窗口大小/窗口
位置下都能自动定位（见 erp_ui.py 的匹配引擎）。

子命令：
  crop   <图片> <form> <名字> <x> <y> <w> <h>   从截图裁一个模板（自动去白边）
  list                                      列出全部模板库
  show    <form>                             列出某库里的模板
  verify <图片> <form> [--threshold 0.72]   离线回归：在给定截图上匹配全部模板
  probe  <图片>                             对截图做 OCR，列出识别到的文字及位置

示例：
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_tpl.py crop logs/forms_window.png MRP工作台 查找 140 580 60 40
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_tpl.py verify logs/forms_window.png MRP工作台
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import erp_ui  # noqa: E402
from erp_common import safe_print  # noqa: E402


def _read(path):
    arr = erp_ui.imread_unicode(path, cv2.IMREAD_UNCHANGED)
    if arr is None:
        raise SystemExit(f"[FAIL] 读不了图片: {path}")
    return arr


def cmd_crop(argv):
    if len(argv) < 6:
        raise SystemExit("用法: crop <图片> <form> <名字> <x> <y> <w> <h>")
    img_path, form, name = argv[0], argv[1], argv[2]
    x, y, w, h = (int(v) for v in argv[3:7])
    arr = _read(img_path)
    H, W = arr.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        raise SystemExit(f"[FAIL] 裁剪区域越界: {x},{y},{w},{h} (图片 {W}x{H})")
    sub = arr[y0:y1, x0:x1]
    store = erp_ui.TemplateStore()
    path = store.add_template(form, name, sub, ref_size=[x1 - x0, y1 - y0],
                              ref_rect=[x0, y0, x1 - x0, y1 - y0],
                              ref_image_size=[arr.shape[1], arr.shape[0]])
    tpl = _read(path)
    safe_print(f"[OK] 模板已保存: {path}  尺寸 {tpl.shape[1]}x{tpl.shape[0]} "
               f"（源区域 {x},{y},{w},{h}）")


def cmd_list(argv):
    store = erp_ui.TemplateStore()
    forms = store.list_forms()
    if not forms:
        safe_print("[提示] 模板库为空，先用 crop 建模板")
        return
    for f in forms:
        tpls = store.templates(f)
        safe_print(f"- {f}: {len(tpls)} 个模板 -> {list(tpls)}")


def cmd_show(argv):
    if not argv:
        raise SystemExit("用法: show <form>")
    store = erp_ui.TemplateStore()
    form = argv[0]
    tpls = store.templates(form)
    if not tpls:
        raise SystemExit(f"[FAIL] 模板库「{form}」为空")
    for name, path in tpls.items():
        arr = _read(path)
        safe_print(f"- {name}: {arr.shape[1]}x{arr.shape[0]}  ({path})")


def cmd_verify(argv):
    thr = 0.72
    if "--threshold" in argv:
        thr = float(argv[argv.index("--threshold") + 1])
    argv = [a for a in argv if a not in ("--threshold", thr)]
    if len(argv) < 2:
        raise SystemExit("用法: verify <图片> <form> [--threshold 0.72]")
    img_path, form = argv[0], argv[1]
    arr = _read(img_path)
    store = erp_ui.TemplateStore()
    tpls = store.templates(form)
    if not tpls:
        raise SystemExit(f"[FAIL] 模板库「{form}」为空")
    safe_print(f"回归测试: {img_path}  模板库「{form}」({len(tpls)} 个)  阈值 {thr}")
    ok = 0
    store = erp_ui.TemplateStore()
    for name, path in tpls.items():
        tpl = _read(path)
        roi = store.roi_for(form, name, (arr.shape[1], arr.shape[0]))
        r = erp_ui.match_template(arr, tpl, threshold=thr, roi=roi)
        if r:
            ok += 1
            safe_print(f"  [命中] {name}: x={r.x} y={r.y} w={r.w} h={r.h} "
                       f"score={r.score:.3f}")
        else:
            safe_print(f"  [未命中] {name}")
    safe_print(f"命中率: {ok}/{len(tpls)}")


def cmd_probe(argv):
    if not argv:
        raise SystemExit("用法: probe <图片>")
    from PIL import Image
    img = Image.open(argv[0])
    items = erp_ui.ocr_text(img)
    if not items:
        safe_print("[提示] 未识别到文字（OCR 未安装或该图无文字）")
        return
    for text, score, (x, y, w, h) in items:
        safe_print(f"  {text!r} score={score:.2f} box=({x},{y},{w},{h})")


COMMANDS = {
    "crop": cmd_crop,
    "list": cmd_list,
    "show": cmd_show,
    "verify": cmd_verify,
    "probe": cmd_probe,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        safe_print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
