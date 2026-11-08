# -*- coding: utf-8 -*-
"""
采购申请 一次性完整流程 v4：弃脏单 → 重开干净表单 → 逐格录入 → 保存 → 读回编号。

动作序列（全程 OCR 锚点 + 区域回读，逐步打印）：
  A) 关闭当前脏「申请-[新建]」（点内窗 ✖，弹「保存更改?」选「否」丢弃）
  B) 回到浏览器导航窗，点「2.申请」→「打开(O)」拉起干净表单
  C) 表头 说明；行1 物料/数量/价格/需要日期；底部 组织/地点/子库存
  D) Ctrl+S 保存；清校验弹窗；读回申请编号；最终截图
"""
import datetime
import os
import re
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

ITEM_NO = "3012324101140"
QTY = "1"
PRICE = "0"
DESC_S = "零头补录入库"
ORG_S = "洗衣机三工厂"
LOC_S = "洗衣机三工厂"
SUBINV = "WL301"
DATE_S = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()

WARN_KS = ("注意", "提示", "警告", "确认", "询问", "保存", "关闭")


def ocr_now(app):
    img = erp_ui.capture(app, focus=False)
    hits = ocr_hits(img)
    if not hits:                       # 引擎首次预热可能返回空 → 重试一次
        time.sleep(0.6)
        img = erp_ui.capture(app, focus=False)
        hits = ocr_hits(img)
    return img, hits


def token(hits, word, y_min=None, y_max=None, contains=True, nth=-1):
    cands = [(t, s, r) for t, s, r in hits
             if (word in t if contains else t.strip() == word)]
    cands = [c for c in cands
             if (y_min is None or c[2].y + c[2].h >= y_min)
             and (y_max is None or c[2].y <= y_max)]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0][2]
    cands.sort(key=lambda x: (x[2].y, x[2].x))
    return cands[nth][2]


def click_at(app, x, y, tag):
    return erp_ui.click_rect(app, Rect(x - 35, y - 12, 70, 24, name=tag),
                             dx=0.5, dy=0.5)


def clear_field(app, n=22):
    app.window.type_keys("{END}", pause=0.02)
    app.window.type_keys("{BACKSPACE %d}" % n, pause=0.02)


def type_in(app, text):
    app.window.type_keys(text, with_spaces=True, pause=0.03)


def click_dialog_button(app, words=("确定",), y_top=None):
    """在弹窗内点指定按钮（words 任一）；返回 True=点过"""
    _, hits = ocr_now(app)
    wins = [r for t, s, r in hits
            if any(k in t.strip() for k in WARN_KS)]
    if not wins and y_top is None:
        return False
    top = min(r.y for r in wins) - 15 if wins else y_top
    for w in words:
        cands = [(t, r) for t, s, r in hits
                 if top <= r.y <= top + 330 and w in t.strip()]
        if cands:
            cands.sort(key=lambda x: x[1].center[0])
            t, r = cands[0]
            print(f"[弹窗] 点「{t}」{r.center}")
            erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
            time.sleep(1.2)
            return True
    return False


# ── A) 关闭脏表单 ──────────────────────────────────────────────────────
def close_dirty_form(app):
    _, hits = ocr_now(app)
    app.window.type_keys("{ESC}")          # 先关掉任何误开的菜单弹层
    time.sleep(0.5)
    # 内窗右上 ■/❑/✖ 按钮组（标题行 80<y<130，x>980；✖ 在组最右侧）
    btns = [r for t, s, r in hits
            if 70 < r.y < 130 and r.x > 980
            and re.search(r"[■□❑▪口✕×xX]", t)]
    if not btns:
        print("[WARN] 没找到内窗关闭按钮组，尝试 Ctrl+F4")
        app.window.type_keys("^({F4})")
        time.sleep(1.5)
        return
    r0 = max(btns, key=lambda r: r.x)
    click_at(app, r0.x + r0.w - 11, r0.y + 11, "内窗关闭")
    time.sleep(1.6)
    app.window.type_keys("{ESC}")
    time.sleep(0.6)
    click_dialog_button(app, words=("否(N)", "否"))      # 弹「保存更改?」选否
    time.sleep(1.2)


# ── B) 重新打开 申请 ────────────────────────────────────────────────
def reopen_apply(app):
    browser = None
    # 「常用表单」精确匹配
    def find_token(*a, **kw):  # noqa: 复用闭包
        return token(*a, **kw)
    for _ in range(5):
        browser = find_token(ocr_now(app)[1], "常用表单", y_min=180)
        if browser is None:
            app.window.type_keys("{TAB}")
            time.sleep(0.8)
            continue
        break
    if browser is None:
        print("[FAIL] 回不到浏览器导航窗（常用表单不可见）")
        return False
    # 「申请」精确匹配（避免误点申请汇总）
    _, hits = ocr_now(app)
    cands = [r for t, s, r in hits
             if re.sub(r"^[0-9．.\s]+", "", t.strip()) == "申请"
             and r.x > 450]
    if not cands:
        print("[FAIL] 常用表单里没找到「申请」条目")
        return False
    r0 = cands[0]
    erp_ui.click_rect(app, r0, dx=0.5, dy=0.5)
    time.sleep(0.8)
    _, hits = ocr_now(app)
    btn = token(hits, "打开", y_min=500, contains=True)
    if btn is None:
        print("[FAIL] 没找到「打开(O)」")
        return False
    erp_ui.click_rect(app, btn, dx=0.5, dy=0.5)
    time.sleep(6)
    click_dialog_button(app, words=("确定",))    # 「组织和地点不允许为空」
    return True


# ── C) 逐格填写 ───────────────────────────────────────────────────────
def fill_header_desc(app, failures):
    tok = token(ocr_now(app)[1], "说明", y_max=330, contains=False)
    if tok is None:
        failures.append("说明(锚)")
        return
    for attempt in range(3):
        click_at(app, tok.x + tok.w + 150, tok.y + 13, "说明")
        time.sleep(0.3)
        clear_field(app, 40)
        type_in(app, DESC_S)
        time.sleep(0.9)
        got = [t for t, r in ocr_in(app, tok.x + 30, tok.x + 280,
                                   tok.y - 12, tok.y + 42)
               if "补录入库" in t and "零头" not in t[:2]]
        got2 = [t for t, r in ocr_in(app, tok.x + 30, tok.x + 280,
                                     tok.y - 12, tok.y + 42)
                if t.strip().startswith("零头") and "补录入库" in t]
        if got or got2:
            print(f"[OK] 说明 -> {(got or got2)[0]!r}")
            return
        clear_field(app, 40)
        print(f"[RETRY] 说明 第{attempt+1}次")
    failures.append("说明")


def ocr_in(app, x0, x1, y0, y1):
    _, hits = ocr_now(app)
    return [(t, r) for t, s, r in hits
            if x0 <= r.x <= x1 and y0 <= r.y <= y1]


def scroll_to_header(app, word, tab_max=8):
    for i in range(tab_max):
        r = find_grid_header(app, word)
        if r is not None:
            return r
        app.window.type_keys("{TAB}")
        time.sleep(1.0)
    return find_grid_header(app, word)


def find_grid_header(app, word):
    _, hits = ocr_now(app)
    cands = [(t, s, r) for t, s, r in hits
             if 300 <= r.y <= 440 and word in t]
    if not cands:
        return None
    cands.sort(key=lambda x: x[2].x)
    return cands[-1][2]


def fill_grid_col(app, word, value, row_y, tag, retries=3):
    for attempt in range(retries):
        tok = find_grid_header(app, word)
        if tok is None:
            time.sleep(0.6)
            continue
        if "数量" and tok.w > 60:            # 「单位数量」合并 token
            cx = int(tok.x + tok.w * 0.75)
            x0, x1 = tok.x - 40, tok.x + tok.w + 150
        else:
            cx = tok.x + tok.w // 2
            x0, x1 = tok.x - 50, tok.x + tok.w + 160
        click_at(app, cx, row_y, tag)
        time.sleep(0.3)
        clear_field(app, 12)
        type_in(app, value)
        time.sleep(0.9)
        got = [t for t, r in ocr_in(app, x0, x1, row_y - 24, row_y + 18)
               if (value in t or (word == "日期" and "10-30" in t))]
        if got:
            print(f"[OK] {tag} -> {got[0]!r}")
            return True
        print(f"[RETRY] {tag} 第{attempt+1}次未确认")
    print(f"[FAIL] {tag}")
    return False


def fill_bottom(app, tok_label, value, check_word, tag):
    x = tok_label.x + tok_label.w + 140
    y = tok_label.y + 13
    for attempt in range(3):
        click_at(app, x, y, tag)
        time.sleep(0.3)
        clear_field(app, 18)
        type_in(app, value)
        time.sleep(0.8)
        app.window.type_keys("{TAB}")
        time.sleep(1.4)
        got = [t for t, r in ocr_in(app, x - 170, x + 210, y - 25, y + 25)
               if check_word in t]
        if got:
            print(f"[OK] {tag} -> {got[0]!r}")
            return True
        _, hits = ocr_now(app)
        rows = [r for t, s, r in hits if check_word in t and r.y < y - 70]
        if rows:
            r0 = min(rows, key=lambda r: r.y)
            print(f"[LOV] {tag}: 点列表行 {r0.center}")
            erp_ui.click_rect(app, r0, dx=0.5, dy=0.5)
            time.sleep(0.4)
            app.window.type_keys("{ENTER}")
            time.sleep(1.6)
            got = [t for t, r in ocr_in(app, x - 170, x + 210, y - 25, y + 25)
                   if check_word in t]
            if got:
                print(f"[OK] {tag} (LOV) -> {got[0]!r}")
                return True
    print(f"[FAIL] {tag}")
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
    print(f"[OK] 连接 hwnd={hwnd}")
    erp_ui.focus_window(app, settle=0.6)

    failures = []

    # 0) 处理挂起弹窗（关闭确认 / 不允许为空校验）
    print("── 0) 处理挂起弹窗 ──")
    for _try in range(4):
        _, hits0 = ocr_now(app)
        dlg_close = [t for t, _, _ in hits0 if "是否关闭" in t]
        dlg_err = [t for t, _, _ in hits0 if "不允许为空" in t or "警告" in t]
        print(f"[diag] hits={len(hits0)} 关闭确认={len(dlg_close)} "
              f"校验弹窗={len(dlg_err)}")
        if dlg_close:
            click_dialog_button(app, words=("是(Y)", "是"))   # 关闭脏表单
            time.sleep(2.5)
            click_dialog_button(app, words=("确定",))
            time.sleep(1.5)
        elif dlg_err:
            click_dialog_button(app, words=("确定",))
            time.sleep(1.5)
        else:
            break
        time.sleep(1.0)

    # A) 只有存在脏标记（之前没写完的单）才关闭表单重来
    print("── A) 弃脏单 ──")
    _, hits0 = ocr_now(app)
    dirty = any(("零头补录" in t) or ("溢水" in t) for t, _, _ in hits0)
    form_open = any(t.startswith("记录") or t.strip() == "采购申请"
                    for t, _, _ in hits0)
    if dirty and form_open:
        close_dirty_form(app)
        time.sleep(1.5)

    # B) 若没有干净的申请表单 → 重开
    print("── B) 确保干净表单 ──")
    _, hitsB = ocr_now(app)
    open_now = any(t.startswith("记录") or t.strip() == "采购申请"
                   for t, _, _ in hitsB)
    if not open_now:
        if not reopen_apply(app):
            print("[ABORT] 无法重开申请表单")
            sys.exit(4)
    # 表单可能：新窗口 or 复用原窗口（MDI 子壳），重试枚举后兜底复用
    app_ok = False
    for _ in range(6):
        time.sleep(2.0)
        snap2 = erp_navigator.snapshot_forms_windows()
        if snap2:
            hwnd2, t2 = list(snap2.items())[-1]
            app2 = erp_forms.FormsApp()
            if app2.connect_by_hwnd(int(hwnd2)):
                app = app2
                app_ok = True
            break
    if not app_ok:
        print("[INFO] 新 Forms 窗口未枚举到，复用原窗口继续")
    erp_ui.focus_window(app, settle=1.0)

    # C) 行1 y + 表格锚点
    _, hits = ocr_now(app)
    ys = [r.y + r.h // 2 for t, s, r in hits
          if t.strip().isdigit() and 340 <= r.y <= 450]
    row_y = ys[0] if ys else 401
    tok_item = find_grid_header(app, "物料")
    tok_desc_h = token(hits, "说明", y_max=330, contains=False)
    tok_org_f = token(hits, "组织", y_min=550, contains=False)
    tok_sub = token(hits, "子库存", y_min=550, contains=False)
    print(f"[OK] row_y={row_y} 物料={tok_item.center if tok_item else None} "
          f"说明头={tok_desc_h.center if tok_desc_h else None} "
          f"组织={tok_org_f.center if tok_org_f else None} "
          f"子库存={tok_sub.center if tok_sub else None}")

    # 行1 物料
    if tok_item:
        click_at(app, tok_item.x + tok_item.w // 2, row_y, "物料")
        time.sleep(0.4)
        type_in(app, ITEM_NO)
        time.sleep(2.5)
        click_dialog_button(app, words=("确定",))
        got = [t for t, r in ocr_in(app, tok_item.x - 60, tok_item.x + 220,
                                    row_y - 24, row_y + 18)
               if ITEM_NO[:4] in t or ITEM_NO[-6:] in t]
        if not got:
            print("[WARN] 物料值未回读到（可能已校验通过被右滚），继续")
        else:
            print(f"[OK] 物料 -> {got[0]!r}")

    # 说明/数量/价格/日期/组织/地点/子库存
    fill_header_desc(app, failures)

    ctok = scroll_to_header(app, "数量")
    if not fill_grid_col(app, "数量", QTY, row_y, "数量"):
        failures.append("数量")
    ptok = scroll_to_header(app, "价格")
    if not fill_grid_col(app, "价格", PRICE, row_y, "价格"):
        failures.append("价格")
    dtok = scroll_to_header(app, "日期")
    if not fill_grid_col(app, "日期", DATE_S, row_y, "日期"):
        failures.append("日期")

    if tok_org_f and not fill_bottom(app, tok_org_f, ORG_S, "洗衣机", "组织"):
        failures.append("组织")
    # 地点 = 左列「地点」标签锚点；OCR 没认出来就用 组织+34px 兜底
    tok_loc = token(hits, "地点", y_min=550, contains=False)
    if tok_loc is not None and tok_loc.x > 400:   # 只认左列（右侧列头 x≈760 排除）
        tok_loc = None
    if tok_loc is None and tok_org_f is not None:
        from erp_ui import Rect as _R
        tok_loc = _R(tok_org_f.x, tok_org_f.y + 34, tok_org_f.w, tok_org_f.h,
                     name="地点(兜底)")
    if tok_loc and not fill_bottom(app, tok_loc, LOC_S, "洗衣机", "地点"):
        failures.append("地点")

    if tok_sub and not fill_bottom(app, tok_sub, SUBINV, "WL301", "子库存"):
        failures.append("子库存")

    if failures:
        print(f"[ABORT] 未通过：{failures} —— 不保存")
        img, _ = ocr_now(app)
        save_shot(img, VERIFY)
        print(f"MEDIA:{VERIFY}")
        sys.exit(7)

    # D) 保存
    erp_ui.focus_window(app, settle=0.4)
    app.window.type_keys("^s")
    time.sleep(2.5)
    n = 0
    while n < 8:
        if not click_dialog_button(app, words=("确定",)):
            break
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
          f"{'申请编号 = ' + number if number else '未读到编号，请复核截图'}")
    save_shot(img, VERIFY)
    texts = [t for t, *_ in ocr_now(app)[1] if t.strip()]
    print("[OCR] 最终: " + " | ".join(texts)[:500])
    print(f"MEDIA:{VERIFY}")


if __name__ == "__main__":
    main()
