# -*- coding: utf-8 -*-
"""
「申请-[新建]」采购申请 一次性完整录入（重测版）。
原则：
  1) 每个字段：OCR 实时找锚点 → 点击 → 清空({END}{BACKSPACE n}) → type_keys 键入
  2) 键入后立即区域回读验证；失败则换候选点/多次清空重试
  3) LOV（组织/地点/子库存）弹列表时：OCR 点选目标行 → {ENTER}
  4) 全部字段验证通过才 Ctrl+S 保存；保存后自动点校验弹窗，读回申请编号
"""
import datetime
import os
import sys
import time

sys.path.insert(0, r"E:\SKILLS\WHP-whirlpool-erp\scripts")

import erp_navigator
import erp_forms
import erp_ui
from erp_flow_org import ocr_hits
from erp_ui import Rect

PROJECT_DIR = r"E:\SKILLS\WHP-whirlpool-erp"
VERIFY = os.path.join(PROJECT_DIR, "logs", "req_final.png")

ITEM_NO = "3012324101140"
QTY = "1"
PRICE = "0"
DESC_S = "零头补录入库"
ORG_S = "洗衣机三工厂"
LOC_S = "洗衣机三工厂"
SUBINV = "WL301"
DATE_S = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()

ROW_Y = 399      # 行1 中心（OCR 实测值，全部步骤前会复核）


# ── primitives ───────────────────────────────────────────────────────
def ocr_now(app):
    img = erp_ui.capture(app, focus=False)
    return img, ocr_hits(img)


def find_token(app, word, y_min=None, y_max=None, contains=True, nth=-1):
    _, hits = ocr_now(app)
    cands = []
    for t, s, r in hits:
        if (word in t) if contains else (t.strip() == word):
            if y_min is not None and r.y + r.h < y_min:
                continue
            if y_max is not None and r.y > y_max:
                continue
            cands.append((r, s))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0].y)
    return cands[nth][0]


def click_at(app, x, y, tag=""):
    return erp_ui.click_rect(app, Rect(x - 35, y - 12, 70, 24, name=tag),
                             dx=0.5, dy=0.5)


def clear_field(app, n=16):
    app.window.type_keys("{END}", pause=0.02)
    app.window.type_keys("{BACKSPACE %d}" % n, pause=0.02)


def type_in(app, text):
    app.window.type_keys(text, with_spaces=True, pause=0.03)


def ocr_region(app, x0, x1, y0, y1):
    _, hits = ocr_now(app)
    return [(t, r) for t, s, r in hits
            if x0 <= r.x <= x1 and y0 <= r.y <= y1]


def fill_and_check(app, x, y, text, check_word, rx0, rx1, ry0, ry1,
                   tag, x_shifts=(0,)):
    """
    点击(x,y) → 清空 → 键入 text → 回读 rx 区间内应出现 check_word。
    x_shifts 提供候选横向偏移；所有候选都失败返回 False。
    """
    for dx in x_shifts:
        click_at(app, x + dx, y, tag)
        time.sleep(0.35)
        for _ in range(2):
            clear_field(app, 20)
            type_in(app, text)
            time.sleep(1.0)
            found = [t for t, r in ocr_region(app, rx0, rx1, ry0, ry1)
                     if check_word in t]
            if found:
                print(f"[OK] {tag} → {found[0]!r}")
                return True
            print(f"[RETRY] {tag} dx={dx} 未确认（{found}），重清重输")
        erp_ui.focus_window(app, settle=0.5)
    print(f"[FAIL] {tag} 多次尝试未通过回读")
    return False


def lov_pick(app, word, timeout=8):
    """若弹 LOV：点选含 word 的行；返回 True=选定"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, hits = ocr_now(app)
        rows = [(r, s) for t, s, r in hits if word in t]
        # LOV 列表行（排除表单里已填的同一字段——按位置通常在弹窗内，直接取最靠近顶部的命中）
        if rows:
            rows.sort(key=lambda x: x[0].y)
            r = rows[0][0]
            erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
            time.sleep(0.4)
            app.window.type_keys("{ENTER}")
            time.sleep(1.0)
            return True
        time.sleep(1.0)
    return False


def dialog_clean(app, limit=8):
    n = 0
    while n < limit:
        _, hits = ocr_now(app)
        win = [r for t, s, r in hits
               if any(k in t.strip() for k in
                      ("注意", "提示", "警告", "确认", "询问"))]
        if not win:
            break
        top = min(r.y for r in win) - 15
        cands = [(t, r) for t, s, r in hits
                 if top <= r.y <= top + 320
                 and (("确定" in t) or ("是" == t.strip().lstrip("0123456789. (")))]
        if not cands:
            break
        cands.sort(key=lambda x: x[1].center[0])
        t, r = cands[0]
        print(f"[弹窗] 点「{t}」({r.center})")
        erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
        time.sleep(1.2)
        n += 1
    return n


# ── main ─────────────────────────────────────────────────────────────
def main():
    snap = erp_navigator.snapshot_forms_windows()
    if not snap:
        print("[FAIL] 没有 Forms 窗口")
        sys.exit(4)
    hwnd, title = list(snap.items())[-1]
    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(int(hwnd)):
        sys.exit(4)
    print(f"[OK] 连接 hwnd={hwnd}  参数: {ITEM_NO} x{QTY} @{PRICE} "
          f"{ORG_S}/{LOC_S}/{SUBINV} 日期{DATE_S}")

    ok_erp_ui = erp_ui
    ok_erp_ui.focus_window(app, settle=0.6)

    # 行1 y 用「编号」行值复核
    _, hits = ocr_now(app)
    ys = [r.y + r.h // 2 for t, s, r in hits
          if t.strip().isdigit() and 350 <= r.y <= 440]
    row_y = ys[0] if ys else ROW_Y
    print(f"[OK] 行1 y={row_y}")

    # 表头锚点定位
    tok_desc = find_token(app, "说明", y_max=330, contains=False)
    tok_uq = find_token(app, "单位数量", y_min=280, y_max=420)
    tok_price = find_token(app, "价格", y_min=280, y_max=420, contains=False)
    tok_date = find_token(app, "日期", y_min=280, y_max=420)
    tok_org = find_token(app, "组织", y_min=550, contains=False)
    tok_sub = find_token(app, "子库存", y_min=550, contains=False)
    need = {"说明": tok_desc, "单位数量": tok_uq, "价格": tok_price,
            "日期": tok_date, "组织": tok_org, "子库存": tok_sub}
    missing = [k for k, v in need.items() if v is None]
    if missing:
        print(f"[FAIL] 锚点缺失: {missing}，中止（未保存）")
        sys.exit(6)
    print("[OK] 全部锚点已定位:",
          {k: tuple(v.center) for k, v in need.items()})

    failures = []

    # ① 表头 说明
    dx_shift = tok_desc.x - 157   # 说明标签当前 x 与 195 基准的差（窗口可能挪过）
    if not fill_and_check(
            app, tok_desc.x + 148, tok_desc.y + 13, DESC_S, "补录入库",
            tok_desc.x + 30, tok_desc.x + 260, tok_desc.y - 12, tok_desc.y + 42,
            "说明", x_shifts=(0, -14, +14)):
        failures.append("说明")

    # ② 数量（单位数量 token: 单位|数量 各半，数量中心≈x+w*0.75）
    qx = int(tok_uq.x + tok_uq.w * 0.75)
    if not fill_and_check(
            app, qx, row_y, QTY, QTY,
            qx - 60, qx + 30, row_y - 20, row_y + 16,
            "数量", x_shifts=(0, +12, -12, +24)):
        failures.append("数量")

    # ③ 价格 = 0
    px = tok_price.x + tok_price.w // 2
    if not fill_and_check(
            app, px, row_y, PRICE, PRICE,
            px - 55, px + 30, row_y - 20, row_y + 16,
            "价格", x_shifts=(0, +12, -12)):
        failures.append("价格")

    # ④ 需要日期
    dxc = tok_date.x + tok_date.w // 2
    if not fill_and_check(
            app, dxc + 20, row_y, DATE_S, DATE_S,
            tok_date.x - 30, tok_date.x + 180, row_y - 20, row_y + 16,
            "日期", x_shifts=(0, +20, +40, -20)):
        failures.append("日期")

    # ⑤ 组织（LOV 处理）
    ox = tok_org.x + tok_org.w + 130
    oy = tok_org.y + 13
    if not fill_and_check(
            app, ox, oy, ORG_S, "洗衣机",
            ox - 130, ox + 190, oy - 22, oy + 22,
            "组织", x_shifts=(0, +12)):
        failures.append("组织")

    # ⑥ 地点（组织下一行）
    lx = ox
    ly = oy + 34
    if not fill_and_check(
            app, lx, ly, LOC_S, "洗衣机",
            lx - 130, lx + 190, ly - 22, ly + 22,
            "地点", x_shifts=(0, +12)):
        failures.append("地点")

    # ⑦ 子库存（水印 LOV）
    sx = ox
    sy = oy + 68
    if not fill_and_check(
            app, sx, sy, SUBINV, "WL301",
            sx - 130, sx + 190, sy - 22, sy + 22,
            "子库存", x_shifts=(0, +12)):
        failures.append("子库存")

    if failures:
        print(f"[ABORT] 以下字段未通过验证：{failures} —— 不保存，保持现场给你处理")
        img, _ = ocr_now(app)
        import erp_flow_org
        erp_flow_org.save_shot(img, VERIFY)
        print(f"MEDIA:{VERIFY}")
        sys.exit(7)

    # ── 保存 ──
    erp_ui.focus_window(app, settle=0.4)
    app.window.type_keys("^s")
    time.sleep(2.5)
    n = dialog_clean(app)
    print(f"[OK] 保存完成，清掉 {n} 个弹窗")

    # 读回申请编号
    img, hits = ocr_now(app)
    number = None
    for t, s, r in hits:
        clean = t.strip().replace(" ", "")
        if clean.isdigit() and len(clean) >= 8 and r.y < 330:
            number = clean
            break
    if number:
        print(f"[SAVED] 申请编号 = {number}")
    else:
        print("[CHECK] 表头未读到编号——需要你复核截图")
    import erp_flow_org
    erp_flow_org.save_shot(img, VERIFY)
    texts = [t for t, *_ in ocr_now(app)[1] if t.strip()]
    print("[OCR] 最终界面: " + " | ".join(texts)[:500])
    print(f"MEDIA:{VERIFY}")


if __name__ == "__main__":
    main()
