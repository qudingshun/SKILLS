# -*- coding: utf-8 -*-
"""
就地修复当前「申请-[新建]」行的字段（解释性一次性脚本）：
  表头 说明   → 清掉重复文本，重置为「零头补录入库」
  行1 数量    → 1
  行1 价格    → 0
  行1 需要日期 → 今天+7（2026-10-30）
  组织/地点/子库存 → 洗衣机三工厂 / 洗衣机三工厂 / WL301
不保存，全部录完输出截图供复核。
"""
import sys
import time

sys.path.insert(0, r"E:\SKILLS\WHP-whirlpool-erp\scripts")

import erp_navigator
import erp_forms
import erp_ui
from erp_flow_org import ocr_hits
from erp_ui import Rect
import win32clipboard


def hits_now(app):
    img = erp_ui.capture(app, focus=False)
    return img, ocr_hits(img)


def paste_text(app, text):
    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
    win32clipboard.CloseClipboard()
    time.sleep(0.15)
    app.window.type_keys("^v")


def check_field(app, word, xmin, xmax, ymin, ymax, expect=True):
    """区域回读：word 应出现在该区域"""
    time.sleep(0.5)
    _, hits = hits_now(app)
    found = [t for t, s, r in hits
             if word in t and xmin <= r.x <= xmax
             and ymin <= r.y <= ymax]
    return found


def main():
    snap = erp_navigator.snapshot_forms_windows()
    hwnd, title = list(snap.items())[-1]
    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(int(hwnd)):
        sys.exit(4)

    # ── ① 表头 说明：点框 → ^a{DEL} → 粘贴 ──
    img, hits = hits_now(app)
    lbl = [r for t, s, r in hits
           if t.strip() == "说明" and r.y < 330]
    if not lbl:
        print("[FAIL] 表头说明标签未找到"); sys.exit(6)
    lb = lbl[0]
    box = Rect(lb.x + lb.w + 6, lb.y - 2, 180, lb.h + 4)
    erp_ui.click_rect(app, box, dx=0.45)
    time.sleep(0.3)
    app.window.type_keys("^a{DEL}")
    paste_text(app, "零头补录入库")
    time.sleep(0.8)
    print("[①说明] 回读:", check_field(app, "零头", lb.x, lb.x + 320,
                                       lb.y - 10, lb.y + 40))

    # ── ② 行1 数量 = 1 ──
    _, hits = hits_now(app)
    uq = [r for t, s, r in hits if t.strip() == "单位数量"]
    if uq:
        uq = uq[0]
        ncols = (uq.w - 8) // 2          # 单位|数量 各半
        qty_cx = uq.x + uq.w - ncols // 2
    else:
        qty_cx = 640
    row_y = 400
    erp_ui.click_rect(app, Rect(qty_cx - 30, row_y, 60, 24), dx=0.5)
    time.sleep(0.3)
    app.window.type_keys("1", pause=0.03)
    time.sleep(0.6)
    print("[②数量] 回读:", check_field(app, "1", qty_cx - 55, qty_cx + 25,
                                       row_y - 18, row_y + 16))

    # ── ③ 行1 价格 = 0 ──
    _, hits = hits_now(app)
    pj = [r for t, s, r in hits if t.strip() == "价格"]
    if not pj:
        print("[FAIL] 价格列头未找到"); sys.exit(6)
    pc = pj[0]
    erp_ui.click_rect(app, Rect(pc.x, row_y, pc.w + 40, 24), dx=0.45)
    time.sleep(0.3)
    app.window.type_keys("0", pause=0.03)
    time.sleep(0.6)
    print("[③价格] 回读:", check_field(app, "0", pc.x - 40, pc.x + pc.w + 20,
                                       row_y - 18, row_y + 16))

    # ── ④ 行1 需要日期 = 2026-10-30（先清掉旧值 1）──
    _, hits = hits_now(app)
    dt = [r for t, s, r in hits if "日期" in t.strip() and r.y < 400]
    if not dt:
        print("[FAIL] 日期列头未找到"); sys.exit(6)
    dc = dt[0]
    erp_ui.click_rect(app, Rect(dc.x, row_y, dc.w + 60, 24), dx=0.4)
    time.sleep(0.3)
    app.window.type_keys("^a{DEL}")
    paste_text(app, "2026-10-30")
    time.sleep(0.8)
    print("[④日期] 回读:", check_field(app, "10-30", dc.x - 40, dc.x + 130,
                                       row_y - 18, row_y + 16))

    # ── ⑤ 底部 组织 / 地点 / 子库存 ──
    _, hits = hits_now(app)
    org = [r for t, s, r in hits if t.strip() == "组织" and r.y > 520]
    if not org:
        print("[FAIL] 组织标签未找到"); sys.exit(6)
    # 组织（左列）
    ob = org[0]
    erp_ui.click_rect(app, Rect(ob.x + ob.w + 6, ob.y - 2, 200, ob.h + 4),
                      dx=0.4)
    time.sleep(0.3)
    app.window.type_keys("^a{DEL}")
    paste_text(app, "洗衣机三工厂")
    time.sleep(1.0)
    _, hits2 = hits_now(app)
    if any(any(k in t.strip() for k in ("注意", "提示", "警告", "LOV"))
           for t, _, _ in hits2):
        # 可能弹了 LOV/提示 —— 留给后续处理
        print("[⑤组织] 弹出了选择/提示窗口，先不点")
    else:
        print("[⑤组织] 回读:", check_field(app, "洗衣机", ob.x, ob.x + 320,
                                           ob.y - 10, ob.y + 40))

    # 地点 = 组织下一行（左列，行距约 34px）
    loc_box = Rect(ob.x + ob.w + 6, ob.y + 32, 200, ob.h + 4)
    erp_ui.click_rect(app, loc_box, dx=0.4)
    time.sleep(0.3)
    app.window.type_keys("^a{DEL}")
    paste_text(app, "洗衣机三工厂")
    time.sleep(1.0)
    _, hits3 = hits_now(app)
    if any(any(k in t.strip() for k in ("注意", "提示", "警告"))
           for t, _, _ in hits3):
        print("[⑤地点] 弹出了选择/提示窗口，先不点")
    else:
        ly = loc_box.y + loc_box.h // 2
        print("[⑤地点] 回读:", check_field(app, "洗衣机", ob.x - 30,
                                           ob.x + 320, ly - 22, ly + 22))

    # 子库存 = 地点下一行（左列）
    sub_box = Rect(ob.x + ob.w + 6, ob.y + 64, 200, ob.h + 4)
    erp_ui.click_rect(app, sub_box, dx=0.4)
    time.sleep(0.3)
    app.window.type_keys("WL301")
    time.sleep(1.0)
    _, hits4 = hits_now(app)
    if any(any(k in t.strip() for k in ("注意", "提示", "警告"))
           for t, _, _ in hits4):
        print("[⑤子库存] 弹出了选择/提示窗口，先不点")
    else:
        sy = sub_box.y + sub_box.h // 2
        print("[⑤子库存] 回读:", check_field(app, "WL301", ob.x - 30,
                                             ob.x + 320, sy - 22, sy + 22))

    from erp_flow_org import save_shot
    img, _ = hits_now(app)
    save_shot(img, r"E:\SKILLS\WHP-whirlpool-erp\logs\req_filled.png")
    print("MEDIA:E:\\SKILLS\\WHP-whirlpool-erp\\logs\\req_filled.png")


if __name__ == "__main__":
    main()
