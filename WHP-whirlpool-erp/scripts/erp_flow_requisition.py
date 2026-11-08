# -*- coding: utf-8 -*-
"""
「申请-[新建]」采购申请 一次性完整录入 v3（目标：一次通过）。

策略（吸取 v2 教训）：
  · 表头「说明」用标签锚点 + 框内点击 + {END}{BACKSPACE n} 清空 + type_keys
    （实测：Ctrl+A/粘贴在 Java 输入框里清不全；type_keys 中文可用）
  · 表格列：从「物料」格 Tab 滚动，目标列头一出现在 OCR 里就点击该列格
    （网格滚随游标，锚点坐标每次现抓，杜绝列缝误点）
  · 组织/地点/子库存：键入后 {ENTER}（LOV 唯一匹配自动选中）；
    若弹列表，OCR 点选目标行再 {ENTER}
  · 每格区域回读验证；任一关键格失败 → 中止保存，保现场输出截图
"""
import datetime
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

ITEM_NO = "3012324101140"      # 物料已在上屏，表头说明/数量/价格/日期/组织等继续录入
QTY = "1"
PRICE = "0"
DESC_S = "零头补录入库"
ORG_S = "洗衣机三工厂"
LOC_S = "洗衣机三工厂"
SUBINV = "WL301"
DATE_S = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()

ROW_Y = 399                    # 行1 数据行中心（初始化时用编号值复核）


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


def clear_field(app, n=18):
    app.window.type_keys("{END}", pause=0.02)
    app.window.type_keys("{BACKSPACE %d}" % n, pause=0.02)


def type_in(app, text):
    app.window.type_keys(text, with_spaces=True, pause=0.03)


def ocr_in(app, x0, x1, y0, y1):
    _, hits = ocr_now(app)
    return [(t, r) for t, s, r in hits
            if x0 <= r.x <= x1 and y0 <= r.y <= y1]


def scroll_to_header(app, word, tab_max=8):
    """Tab 滚动网格直到列头 word 在 OCR 里可见。返回 (token_rect) 或 None"""
    for i in range(tab_max):
        r = find_token(app, word, y_min=280, y_max=420)
        if r is not None:
            return r
        app.window.type_keys("{TAB}")
        time.sleep(1.0)
    return find_token(app, word, y_min=280, y_max=420)


def fill_grid_col(app, word, value, row_y, xr, tag, retries=3):
    """列头现抓锚点 → 点格 → 清空→键入→区域回读验证（带横向重试）"""
    x0, x1 = xr
    for attempt in range(retries):
        tok = find_token(app, word, y_min=280, y_max=420,
                         contains=(word != "数量"))
        if tok is None:
            continue
        cx = tok.x + tok.w // 2
        click_at(app, cx, row_y, tag)
        time.sleep(0.3)
        clear_field(app, 18)
        type_in(app, value)
        time.sleep(0.9)
        got = [t for t, r in ocr_in(app, x0, x1, row_y - 22, row_y + 18)
               if value in t or (word == "日期" and "10-30" in t)]
        if got:
            print(f"[OK] {tag} -> {got[0]!r}")
            return True
        print(f"[RETRY] {tag} 第{attempt+1}次未确认（{got}）")
    print(f"[FAIL] {tag} 多次尝试未通过")
    return False


def fill_bottom(app, tok_label, value, check_word, tag, y_off,
                retries=2, usel_tab=True):
    """底部标签右侧框：点击→清空→键入→(回车处理 LOV)→回读验证"""
    x = tok_label.x + tok_label.w + 140
    y = tok_label.y + 13 + y_off
    for attempt in range(retries):
        click_at(app, x, y, tag)
        time.sleep(0.3)
        clear_field(app, 18)
        type_in(app, value)
        time.sleep(0.8)
        if usel_tab:
            app.window.type_keys("{TAB}")
        time.sleep(1.2)
        got = [t for t, r in ocr_in(app, x - 150, x + 190,
                                    y - 24, y + 24)
               if check_word in t]
        if got:
            print(f"[OK] {tag} -> {got[0]!r}")
            return True
        # 可能弹了 LOV：点列表中最靠上的目标行 → ENTER
        _, hits = ocr_now(app)
        rows = [r for t, s, r in hits if check_word in t and r.y < y - 60]
        if rows:
            r0 = min(rows, key=lambda r: r.y)
            print(f"[LOV] {tag}: 点列表行 {r0.center} 后回车")
            erp_ui.click_rect(app, r0, dx=0.5, dy=0.5)
            time.sleep(0.4)
            app.window.type_keys("{ENTER}")
            time.sleep(1.4)
            continue
        clear_field(app, 20)          # 失败时先清干净再重试
    print(f"[FAIL] {tag} 未通过回读")
    return False


def main():
    snap = erp_navigator.snapshot_forms_windows()
    if not snap:
        print("[FAIL] 没有 Forms 窗口")
        sys.exit(4)
    hwnd, title = list(snap.items())[-1]
    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(int(hwnd)):
        sys.exit(4)
    print(f"[OK] 连接 hwnd={hwnd}  参数: {QTY} @{PRICE} {ORG_S}/{LOC_S}/"
          f"{SUBINV} 日期={DATE_S} 说明={DESC_S}")
    erp_ui.focus_window(app, settle=0.6)

    failures = []

    # ── 0) 行1 y 复核 + 表头锚点 ──
    _, hits = ocr_now(app)
    ys = [r.y + r.h // 2 for t, s, r in hits
          if t.strip().isdigit() and 350 <= r.y <= 440]
    row_y = ys[0] if ys else ROW_Y
    tok_desc = find_token(app, "说明", y_max=330, contains=False)
    tok_org_f = find_token(app, "组织", y_min=550, contains=False)
    tok_org_g = find_token(app, "组织", y_min=550,
                           contains=False, nth=0)
    tok_sub = find_token(app, "子库存", y_min=550, contains=False)
    print(f"[OK] row_y={row_y} 说明锚={tok_desc.center if tok_desc else None} "
          f"组织锚={[r.center for r in (tok_org_f,) if r]} "
          f"子库存锚={tok_sub.center if tok_sub else None}")

    # ── 1) 表头 说明（清掉双拼脏数据）──
    if tok_desc:
        for attempt in range(3):
            click_at(app, tok_desc.x + tok_desc.w + 150,
                     tok_desc.y + 13, "说明")
            time.sleep(0.3)
            clear_field(app, 40)
            type_in(app, DESC_S)
            time.sleep(0.9)
            got = [t for t, r in ocr_in(app, tok_desc.x + 30,
                                        tok_desc.x + 280,
                                        tok_desc.y - 12, tok_desc.y + 42)
                   if "补录入库" in t]
            if got:
                print(f"[OK] 说明 -> {got[0]!r}")
                break
            clear_field(app, 40)
            print(f"[RETRY] 说明 第{attempt+1}次未确认")
        else:
            failures.append("说明")

    # ── 2) 行1：数量（先 Tab 滚出可见）──
    # 游标先落到网格里的物料格（值已正确，只点击定位）
    tok_item = find_token(app, "物料", y_min=280, y_max=420, contains=False)
    if tok_item:
        click_at(app, tok_item.x + tok_item.w // 2, row_y, "物料定位")
        time.sleep(0.4)
    else:
        click_at(app, tok_desc.x + tok_desc.w + 150, row_y, "网格落点")
    ctok = scroll_to_header(app, "数量")
    if not fill_grid_col(app, "数量", QTY, row_y,
                         (ctok.x - 60, ctok.x + 40) if ctok else (500, 700),
                         "数量"):
        failures.append("数量")

    # ── 3) 价格 = 0 ──
    ptok = scroll_to_header(app, "价格")
    if not fill_grid_col(app, "价格", PRICE, row_y,
                         (ptok.x - 55, ptok.x + 40) if ptok else None,
                         "价格"):
        failures.append("价格")

    # ── 4) 需要日期 ──
    dtok = scroll_to_header(app, "日期")
    if not fill_grid_col(app, "日期", DATE_S, row_y,
                         (dtok.x - 60, dtok.x + 200) if dtok else None,
                         "日期"):
        failures.append("日期")

    # ── 5) 组织 ──
    if tok_org_f and not fill_bottom(app, tok_org_f, ORG_S, "洗衣机",
                                     "组织", y_off=0):
        failures.append("组织")

    # ── 6) 地点（组织下一行的框）──
    if tok_org_f and not fill_bottom(app, tok_org_f, LOC_S, "洗衣机",
                                     "地点", y_off=34):
        failures.append("地点")

    # ── 7) 子库存 ──
    if tok_sub and not fill_bottom(app, tok_sub, SUBINV, "WL301",
                                   "子库存", y_off=0):
        failures.append("子库存")

    if failures:
        print(f"[ABORT] 未通过：{failures} —— 不保存，保持现场")
        img, _ = ocr_now(app)
        save_shot(img, VERIFY)
        print(f"MEDIA:{VERIFY}")
        sys.exit(7)

    # ── 保存 ──
    erp_ui.focus_window(app, settle=0.4)
    app.window.type_keys("^s")
    time.sleep(2.5)
    # 清校验弹窗
    n = 0
    while n < 8:
        _, hits = ocr_now(app)
        win = [r for t, s, r in hits
               if any(k in t.strip() for k in
                      ("注意", "提示", "警告", "确认", "询问"))]
        if not win:
            break
        top = min(r.y for r in win) - 15
        cands = [(t, r) for t, s, r in hits
                 if top <= r.y <= top + 320 and "确定" in t]
        if not cands:
            break
        cands.sort(key=lambda x: x[1].center[0])
        t, r = cands[0]
        print(f"[弹窗] 点「{t}」{r.center}")
        erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
        time.sleep(1.2)
        n += 1
    print(f"[OK] 保存后清掉 {n} 个弹窗")

    # 读回编号
    img, hits = ocr_now(app)
    number = None
    for t, s, r in hits:
        clean = t.strip().replace(" ", "")
        if clean.isdigit() and len(clean) >= 8 and r.y < 330:
            number = clean
            break
    print(f"[{'SAVED' if number else 'CHECK'}] "
          f"{'申请编号 = ' + number if number else '未读到编号，请复核'}")
    save_shot(img, VERIFY)
    texts = [t for t, *_ in ocr_now(app)[1] if t.strip()]
    print("[OCR] 最终: " + " | ".join(texts)[:500])
    print(f"MEDIA:{VERIFY}")


if __name__ == "__main__":
    main()
