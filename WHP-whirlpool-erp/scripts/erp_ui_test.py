#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_ui_test - 模板库离线回归测试（不连 ERP）

目的：验证「与屏幕分辨率、窗口大小、窗口位置无关」这一核心诉求。
做法：把基线截图做多种变换，模拟不同环境下同一个界面的呈现，再跑模板匹配：

  1) 缩放 0.75 / 0.9 / 1.1 / 1.25   → 模拟分辨率 / DPI 变化
  2) 平移 + 画布填充               → 模拟窗口在屏幕上的位置移动
  3) 亮度/对比度轻微扰动            → 模拟主题/显示器差异
  4) JPEG 压缩噪声                 → 模拟截图质量差异

用法：
  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ui_test.py <图片> <form>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

import erp_ui  # noqa: E402
from erp_common import safe_print  # noqa: E402


def _variants(base):
    """生成 (描述, 图) 列表"""
    out = []
    H, W = base.shape[:2]

    out.append(("原图 1.0x", base))

    for s in (0.75, 0.9, 1.1, 1.25):
        out.append((f"缩放 {s}x",
                    cv2.resize(base, (int(W * s), int(H * s)),
                               interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR)))

    # 平移（模拟窗口移动到屏幕别处）
    for dx, dy in ((300, 0), (0, 220), (-120, 160)):
        M = np.float32([[1, 0, dx], [0, 1, dy]])
        out.append((f"平移 ({dx},{dy})", cv2.warpAffine(base, M, (W, H),
                                                        borderValue=(255, 255, 255))))

    # 亮度/对比度扰动
    out.append(("亮度 +12", np.clip(base.astype(np.int16) + 12, 0, 255).astype(np.uint8)))
    out.append(("对比度 0.85", np.clip((base.astype(np.float32) - 128) * 0.85 + 128,
                                       0, 255).astype(np.uint8)))

    # JPEG 噪声
    ok, enc = cv2.imencode(".jpg", base, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if ok:
        out.append(("JPEG q70", cv2.imdecode(enc, cv2.IMREAD_COLOR)))
    return out


def main():
    if len(sys.argv) < 3:
        safe_print(__doc__)
        sys.exit(1)
    img_path, form = sys.argv[1], sys.argv[2]
    thr = float(os.environ.get("WP_UI_THRESHOLD", "0.72"))

    base = erp_ui.imread_unicode(img_path, cv2.IMREAD_COLOR)
    if base is None:
        safe_print(f"[FAIL] 读不了图片: {img_path}")
        sys.exit(1)

    store = erp_ui.TemplateStore()
    tpls = store.templates(form)
    if not tpls:
        safe_print(f"[FAIL] 模板库「{form}」为空")
        sys.exit(1)

    tpl_arrs = {}
    for name, path in tpls.items():
        a = erp_ui.imread_unicode(path, cv2.IMREAD_UNCHANGED)
        if a is not None:
            tpl_arrs[name] = a

    total = hit = 0
    detail = []
    for desc, img in _variants(base):
        line = []
        for name, tpl in tpl_arrs.items():
            r = erp_ui.match_template(img, tpl, threshold=thr)
            total += 1
            if r:
                hit += 1
                line.append(f"{name}[{r.score:.2f}@({r.x},{r.y})]")
            else:
                line.append(f"{name}[MISS]")
        detail.append((desc, line))
        safe_print(f"  {desc:<18} " + "  ".join(line))

    safe_print(f"总计命中: {hit}/{total}  ({hit * 100.0 / max(1, total):.1f}%)")
    sys.exit(0 if hit == total else 2)


if __name__ == "__main__":
    main()
