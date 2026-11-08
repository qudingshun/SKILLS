#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoke_erp - WHP-whirlpool-erp 自检脚本

用法：
  E:/SKILLS/.venv/Scripts/python.exe scripts/smoke_erp.py            # 离线自检（不连 ERP）
  E:/SKILLS/.venv/Scripts/python.exe scripts/smoke_erp.py --live     # 连真 ERP 跑一遍全链路

离线自检项：
  1. 依赖与模块可导入
  2. 密码能否解密（不打印明文）
  3. 模板库清单
  4. 模板离线回归（缩放/平移/亮度/JPEG 变体下的命中率）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_IMG = os.path.join(PROJECT_DIR, "logs", "forms_window.png")

FAILURES = []


def ok(msg):
    print(f"  [OK] {msg}")


def bad(msg):
    FAILURES.append(msg)
    print(f"  [FAIL] {msg}")


def check_imports():
    print("[1/4] 模块与依赖")
    for m in ("cv2", "numpy", "PIL", "pywinauto", "win32com.client"):
        try:
            __import__(m)
            ok(f"依赖可用: {m}")
        except Exception as e:
            bad(f"依赖缺失: {m} ({e})")
    for m in ("erp_common", "erp_secure_config", "erp_ie11", "erp_navigator",
              "erp_forms", "erp_ui", "erp_tpl"):
        try:
            __import__(m)
            ok(f"模块可导入: {m}")
        except Exception as e:
            bad(f"模块导入失败: {m} ({e})")


def check_password():
    print("[2/4] 密码解密（不打印明文）")
    try:
        from erp_common import get_erp_password
        pwd = get_erp_password()
        if pwd:
            ok(f"密码可解密，长度 {len(pwd)}")
        else:
            bad("密码未设置或无法解密（跑 erp_secure_config.py 设置）")
    except Exception as e:
        bad(f"密码检查异常: {e}")


def check_templates():
    print("[3/4] 模板库")
    try:
        import erp_ui
        store = erp_ui.TemplateStore()
        forms = store.list_forms()
        if not forms:
            bad("模板库为空（用 erp_tpl.py crop 建模板）")
            return
        for f in forms:
            tpls = store.templates(f)
            ok(f"「{f}」: {len(tpls)} 个模板 -> {list(tpls)}")
    except Exception as e:
        bad(f"模板库检查异常: {e}")


def check_regression():
    print("[4/4] 模板离线回归")
    if not os.path.exists(BASELINE_IMG):
        bad(f"缺少基准截图: {BASELINE_IMG}")
        return
    try:
        import erp_ui
        store = erp_ui.TemplateStore()
        forms = store.list_forms()
        if not forms:
            bad("模板库为空，跳过回归")
            return
        import cv2
        base = erp_ui.imread_unicode(BASELINE_IMG, cv2.IMREAD_COLOR)
        for form in forms:
            tpls = store.templates(form)
            hit = total = 0
            for name, path in tpls.items():
                tpl = erp_ui.imread_unicode(path, cv2.IMREAD_UNCHANGED)
                for desc, img in _variants(base):
                    r = erp_ui.match_template(img, tpl, threshold=0.72)
                    total += 1
                    if r:
                        hit += 1
            pct = hit * 100.0 / max(1, total)
            if hit == total:
                ok(f"「{form}」回归命中 {hit}/{total} ({pct:.0f}%)")
            else:
                bad(f"「{form}」回归命中 {hit}/{total} ({pct:.0f}%)")
    except Exception as e:
        bad(f"回归测试异常: {e}")


def _variants(base):
    import cv2
    import numpy as np
    out = [("orig", base)]
    H, W = base.shape[:2]
    for s in (0.75, 1.25):
        out.append((f"s{s}", cv2.resize(base, (int(W * s), int(H * s)),
                                        interpolation=cv2.INTER_AREA if s < 1
                                        else cv2.INTER_LINEAR)))
    M = np.float32([[1, 0, 300], [0, 1, 220]])
    out.append(("shift", cv2.warpAffine(base, M, (W, H), borderValue=(255, 255, 255))))
    out.append(("bright", np.clip(base.astype(np.int16) + 12, 0, 255).astype(np.uint8)))
    ok, enc = cv2.imencode(".jpg", base, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    if ok:
        out.append(("jpeg", cv2.imdecode(enc, cv2.IMREAD_COLOR)))
    return out


def run_live():
    print("[LIVE] 连接真实 ERP，拉起 MRP 工作台并识别界面元素")
    import erp_navigator
    import erp_ui
    import erp_ie11
    resp = "PO,SANYO合肥三洋物料计划员"
    func = "MRP计划员工作台"
    form = erp_ui.form_id(resp, func)
    shot = os.path.join(PROJECT_DIR, "logs", "smoke_live.png")
    app = None
    try:
        app = erp_navigator.open_function(resp, func, timeout=150,
                                          shot_path=shot, close_ie=False)
        if app is None:
            bad("Forms 拉起失败")
            return
        ok("Forms 窗口已拉起")
        found = erp_ui.locate_all(app, form)
        if not found:
            bad("未识别到任何界面元素")
        else:
            for name, r in found.items():
                ok(f"识别「{name}」相对({r.x},{r.y},{r.w},{r.h}) 置信度={r.score:.3f}")
        print(f"MEDIA:{os.path.abspath(shot)}")
    finally:
        # 自检结束收口：注销 EBS + 关闭全部 IE/Forms，不留浏览器
        erp_ie11.close_all(logout=True)


def main():
    live = "--live" in sys.argv
    print("=" * 60)
    print("WHP-whirlpool-erp 自检")
    print("=" * 60)
    if live:
        run_live()
    else:
        check_imports()
        check_password()
        check_templates()
        check_regression()
    print("-" * 60)
    if FAILURES:
        print(f"自检未通过：{len(FAILURES)} 项失败")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("自检全部通过")
    sys.exit(0)


if __name__ == "__main__":
    main()
