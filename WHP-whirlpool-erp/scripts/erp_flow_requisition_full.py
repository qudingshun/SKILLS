#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采购申请「批量全流程」——登录 → 逐张单据（N 行）录入 → 校验 → 保存 → 审批提交 → 退出。

支持两种场景（可混用）：
  A. 一张采购申请单里 N 个物料（多行）
  B. 一次跑多张采购申请单，每张单有各自的「表头说明」和各自的物料行

════════════════ 用法 ════════════════
1) 一张单、多行（--req 可重复，每出现一次 = 一张单）
   python scripts/erp_flow_requisition_full.py \
       --req "零头补录入库|3012324101140:1,3000000000000:2"

2) 多张单，各自说明（每张单一行或 N 行）
   python scripts/erp_flow_requisition_full.py \
       --req "零头补录入库|3012324101140:1" \
       --req "备用件补库|3000000000001:3,3000000000002:1"

3) JSON 计划（复杂场景推荐，支持每行单独价格/日期）
   python scripts/erp_flow_requisition_full.py --plan plan.json
   plan.json:
   [
     {"desc": "零头补录入库",
      "lines": [{"item": "3012324101140", "qty": "1"},
                {"item": "3000000000000", "qty": "2"}]},
     {"desc": "备用件补库",
      "lines": [{"item": "3000000000001", "qty": "3", "date": "2026-11-01"}]}
   ]

4) 单行简写（兼容旧用法）
   ... --item 3012324101140 --qty 1

简写行语法： 物料[:数量[:价格[:需要日期]]]
  「,:|」都是分隔符，物料号与数量**每次由调用方传入，脚本不写死**

════════════════ 流程 ════════════════
  登录 EBS（复用已登录窗口）
  └ 对每张单：
      展开职责 → 读「更改组织」→ 新窗口承载 applet → 选工厂
      → 常用表单「2.申请」→ 打开(O) →「申请-[新建]」
      → 逐行录入（行高由截图网格线实时测量，不写死）
      → 表头说明 + 组织/地点/子库存
      → 逐行+逐字段校验（缺失自动补填 3 轮，仍缺则整单不保存）
      → Ctrl+S 保存 → 读回编号
      → 审批(A)... → 勾「提交以供审批(S)」→ 确定(Q) → 确认
      → 关掉该 applet 窗口，释放内存，跑下一张
  全部完成 → 注销 + 关闭 IE（--keep-ie 保留现场）

════════════════ 校验说明 ════════════════
  Forms 里的细数字（1 / 0）用 OCR 会读成 T，故：
    · 数量 / 价格 → 「单元格像素 + 连通域位数」判定（空=0，填了=位数）
    · 说明 / 日期 / 组织 / 地点 / 子库存 → OCR 回读
    · 物料 → 以 EBS 自动带出的行说明为证据 + 错误弹窗检测
  --self-test [PNG]  用历史截图离线验证校验逻辑，不连 ERP、不产生单据
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import erp_ie11
import erp_jws
import erp_navigator
import erp_forms
import erp_ui
from erp_flow_org import ocr_hits, save_shot
from erp_ui import Rect

# ── 固定口径（可用命令行覆盖） ─────────────────────────────────────
RESP = "PO,SANYO合肥三洋物料计划员"
FUNC_ORG = "更改组织"
WORD_APPLY = "申请"                 # 常用表单里的「2.申请」，整词匹配排除「1.申请汇总」
FACTORY = "洗衣机三工厂"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(PROJECT_DIR, "logs")
os.makedirs(LOGS, exist_ok=True)

WARN_KS = ("注意", "提示", "警告", "确认", "询问", "保存", "关闭", "不允许为空", "错误")
ERR_KS = ("无效", "不存在", "错误", "不能为空", "必填", "不一致", "失败")

GRID_Y0, GRID_Y1 = 330, 470          # 行网格表头纵向区间
ROW_DY = 1.55                        # 行1中心 ≈ 表头 y + 表头 h * ROW_DY
DEFAULT_ROW_STEP = 36                # 行高兜底值（2560x1600 / 100% 缩放实测）


# =====================================================================
# 基础工具
# =====================================================================
def log(msg):
    print(msg, flush=True)


def force_foreground(hwnd) -> bool:
    """把窗口可靠置前（AttachThreadInput + SetForegroundWindow）。

    自动化进程默认没有前台激活权限，普通 SetForegroundWindow 会失败，
    导致 Java applet 的 SunAwtFrame 停在离屏位置不渲染（截图抓到桌面）。
    """
    try:
        import ctypes
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hwnd = int(hwnd)
        if not u32.IsWindow(hwnd):
            return False
        my_tid = k32.GetCurrentThreadId()
        tgt_tid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(tgt_tid))
        tgt_tid = int(tgt_tid.value)
        if tgt_tid and tgt_tid != my_tid:
            u32.AttachThreadInput(my_tid, tgt_tid, True)
        try:
            u32.ShowWindow(hwnd, 9)                 # SW_RESTORE
            u32.SetForegroundWindow(hwnd)
        finally:
            if tgt_tid and tgt_tid != my_tid:
                u32.AttachThreadInput(my_tid, tgt_tid, False)
        time.sleep(0.4)
        return True
    except Exception as e:
        log(f"[WARN] force_foreground 失败: {e}")
        return False


def get_ie_hwnd(ie, tries: int = 6, delay: float = 1.0):
    """新窗口导航后 HWND 不一定立刻可用，带重试地取 COM 属性。"""
    import win32gui
    for i in range(1, max(1, tries) + 1):
        try:
            hwnd = int(ie.HWND)
            if win32gui.IsWindow(hwnd):
                return hwnd
        except Exception as e:
            log(f"[INFO] 读取 ie.HWND 第{i}次失败({e}), {delay}s 后重试")
        time.sleep(delay)
    return None


def ie_frame_hwnds():
    """当前所有可见 IEFrame 顶层窗口 HWND（COM 的 ie.HWND 读不出来时的兜底）。"""
    import win32gui
    out = []

    def _cb(h, _):
        try:
            if win32gui.IsWindowVisible(h) and win32gui.GetClassName(h) == "IEFrame":
                out.append(h)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(_cb, None)
    return out


def grab(app, focus=False, tries=2):
    for _ in range(max(1, tries)):
        img = erp_ui.capture(app, focus=focus)
        if img is not None:
            return img
        time.sleep(0.6)
    return None


def look(app, focus=False, tries=3):
    """截图 + OCR，空结果自动重试（OCR 引擎首次调用可能返回空）。"""
    img, hits = None, []
    for _ in range(max(1, tries)):
        img = grab(app, focus=focus)
        if img is not None:
            hits = ocr_hits(img)
        if hits:
            break
        time.sleep(0.7)
    return img, hits


def to_bgr(img):
    import cv2
    import numpy as np
    return cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def find_tok(hits, word, y_min=None, y_max=None, x_min=None, x_max=None,
             exact=False, nth=-1):
    """返回 (text, score, Rect) 或 None。"""
    cands = []
    for t, s, r in hits:
        ok = (t.strip() == word) if exact else (word in t)
        if not ok:
            continue
        if y_min is not None and r.y + r.h < y_min:
            continue
        if y_max is not None and r.y > y_max:
            continue
        if x_min is not None and r.x + r.w < x_min:
            continue
        if x_max is not None and r.x > x_max:
            continue
        cands.append((t, s, r))
    if not cands:
        return None
    cands.sort(key=lambda x: (x[2].y, x[2].x))
    return cands[nth]


def click_at(app, x, y, tag, w=70, h=24):
    return erp_ui.click_rect(app, Rect(x - w // 2, y - h // 2, w, h, name=tag),
                             dx=0.5, dy=0.5)


def clear_field(app, n=20):
    app.window.type_keys("{END}", pause=0.02)
    app.window.type_keys("{BACKSPACE %d}" % n, pause=0.02)


def type_in(app, text):
    app.window.type_keys(text, with_spaces=True, pause=0.03)


def norm_digits(s):
    return "".join(ch for ch in s if ch.isdigit())


def norm_code(s):
    """编码归一：大写，O->0，I->1（OCR 常把 0 读成 O）。"""
    s = (s or "").upper()
    return s.replace("O", "0").replace("I", "1")


# =====================================================================
# 数字单元格校验（细数字 OCR 不可靠，改用像素 + 连通域位数）
# =====================================================================
def cell_stats(bgr, x0, y0, x1, y1, inset=5):
    """返回 (暗像素占比, 字符连通域个数)。空=0、有内容=数字位数。"""
    import cv2
    import numpy as np
    H, W = bgr.shape[:2]
    x0, x1 = max(0, x0 + inset), min(W, x1 - inset)
    y0, y1 = max(0, y0 + inset), min(H, y1 - inset)
    if x1 - x0 < 6 or y1 - y0 < 6:
        return 0.0, 0
    crop = bgr[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    ratio = float((gray < 128).mean())
    bw = cv2.threshold(gray, 0, 255,
                       cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    n, _lab, stats, _cent = cv2.connectedComponentsWithStats(bw, 8)
    hh = crop.shape[0]
    cnt = 0
    for s in stats[1:]:
        x, y, w, h, area = int(s[0]), int(s[1]), int(s[2]), int(s[3]), int(s[4])
        if w <= 2 or x <= 1:                 # 单元格边框/竖线
            continue
        if h < 0.40 * hh or area < 6:
            continue
        cnt += 1
    return ratio, cnt


def numeric_cell_filled(bgr, band, row_y, value):
    """数字单元格是否已填且位数正确。返回 (ok, (占比, 实测位数, 期望位数))。"""
    x0, x1 = band
    ratio, cnt = cell_stats(bgr, x0, row_y - 17, x1, row_y + 15)
    want = sum(ch.isdigit() for ch in value)
    ok = ratio > 0.0015 and (cnt == want or (want <= 1 and cnt == 0))
    return ok, (ratio, cnt, want)


def checkbox_checked(bgr, chk):
    """勾选框像素判定：token 左侧方框内部是否有笔画。"""
    import cv2
    cx = int(chk.x + chk.h * 0.35)
    cy = int(chk.y + chk.h * 0.5)
    x0, y0 = cx - 4, cy - 6
    crop = bgr[max(0, y0):y0 + 12, max(0, x0):x0 + 8]
    if crop.size == 0:
        return None, 0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    dark = int((gray < 128).sum())
    return dark >= 6, dark


# =====================================================================
# 弹窗
# =====================================================================
def dismiss_dialogs(app, labels=("确定", "是(Y)", "是"), max_n=4, y_top=None):
    done = 0
    for _ in range(max_n):
        img, hits = look(app)
        if not hits:
            break
        marks = [r for t, s, r in hits if any(k in t for k in WARN_KS)]
        top = y_top
        if marks:
            top = min(r.y for r in marks) - 20
        if top is None:
            break
        cands = [(t, r) for t, s, r in hits
                 if top <= r.y <= top + 340 and any(lb in t for lb in labels)]
        if not cands:
            break
        cands.sort(key=lambda x: (x[1].y, x[1].center[0]))
        t, r = cands[0]
        log(f"[弹窗] 点「{t.strip()}」{r.center}")
        erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
        time.sleep(1.2)
        done += 1
    return done


def dialog_is_error(hits, top, bottom):
    for t, s, r in hits:
        if top - 10 <= r.y <= bottom + 10 and any(k in t for k in ERR_KS):
            return t
    return None


# =====================================================================
# 布局识别
# =====================================================================
def detect_row_step(bgr, row1_y, default=DEFAULT_ROW_STEP):
    """用行网格的横向分隔线实测行高（DPI 变化也能自适应）。"""
    import cv2
    H, W = bgr.shape[:2]
    x0, x1 = 90, min(W - 40, 1150)
    y0, y1 = max(0, row1_y - 45), min(H, row1_y + 240)
    sub = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    prof = (sub < 200).mean(axis=1)
    ys = []
    for i, v in enumerate(prof):
        if v > 0.55:
            y = y0 + i
            if not ys or y - ys[-1] > 3:
                ys.append(y)
    diffs = [b - a for a, b in zip(ys, ys[1:]) if 20 <= b - a <= 90]
    if len(diffs) >= 2:
        diffs.sort()
        mid = diffs[len(diffs) // 2]
        return int(round(mid))
    return default


def layout_from(hits):
    """返回布局锚点 dict；进不去申请表单时返回 None。"""
    h_desc = find_tok(hits, "说明", y_min=GRID_Y0, y_max=GRID_Y1, exact=True)
    h_qty = find_tok(hits, "数量", y_min=GRID_Y0, y_max=GRID_Y1)
    h_price = find_tok(hits, "价格", y_min=GRID_Y0, y_max=GRID_Y1)
    h_date = find_tok(hits, "需要日期", y_min=GRID_Y0, y_max=GRID_Y1)
    if not (h_desc and h_qty and h_price and h_date):
        return None

    qr = h_qty[2]
    pr = h_price[2]
    if "单位" in h_qty[0] and "数量" in h_qty[0]:      # 被 OCR 合并成「单位数量」
        q_band = (qr.x + qr.w - 60, pr.x - 12)
    else:
        q_band = (qr.x - 12, qr.x + qr.w + 60)
    lay = {
        "h_desc": h_desc[2],
        "h_qty": qr,
        "h_price": pr,
        "h_date": h_date[2],
        "row1_y": int(qr.y + qr.h * ROW_DY),
        "q_band": q_band,
        "p_band": (pr.x - 12, pr.x + pr.w + 50),
        "d_band": (h_date[2].x - 12, h_date[2].x + h_date[2].w + 170),
        "item_x": find_tok(hits, "物料", y_min=GRID_Y0, y_max=GRID_Y1)
                  and find_tok(hits, "物料", y_min=GRID_Y0, y_max=GRID_Y1)[2].center[0],
        "cat_x": find_tok(hits, "类别", y_min=GRID_Y0, y_max=GRID_Y1)
                 and find_tok(hits, "类别", y_min=GRID_Y0, y_max=GRID_Y1)[2].center[0],
    }
    # 表头「说明」标签（y<330 的那个）
    hdr = find_tok(hits, "说明", y_max=330, exact=True)
    lay["hdr_desc"] = hdr[2] if hdr else None
    return lay


# =====================================================================
# 视图 / 网格实测
#   表格横向滚动位置会随焦点漂移，**列坐标绝不能缓存**。
#   每次操作前用「表头文字 + 网格竖线」现测列中心。
# =====================================================================
def view_cols(hits):
    """当前视图的表头 token：[(text, x, x+w, Rect)]，按 x 排序。"""
    out = []
    for t, s, r in hits:
        if GRID_Y0 <= r.y <= 395:
            out.append((t.strip(), r.x, r.x + r.w, r))
    out.sort(key=lambda z: z[1])
    return out


def _grid_bounds(bgr, y0=398, y1=468):
    """垂直网格线 x 坐标（合并 1~2px 的双边缘）。"""
    import cv2
    H, W = bgr.shape[:2]
    x0, x1 = 60, min(W - 20, 1140)
    band = cv2.cvtColor(bgr[max(0, y0):min(H, y1), x0:x1], cv2.COLOR_BGR2GRAY)
    frac = (band < 235).mean(axis=0)
    peaks, x = [], 0
    while x < len(frac):
        if frac[x] > 0.80:
            j = x
            while j + 1 < len(frac) and frac[j + 1] > 0.80:
                j += 1
            peaks.append(x0 + (x + j) // 2)
            x = j + 1
        else:
            x += 1
    merged = []
    for p in peaks:
        if merged and p - merged[-1] <= 6:
            merged[-1] = (merged[-1] + p) // 2
        else:
            merged.append(p)
    return merged


def _seg_for(bounds, token, name):
    """给表头 token 找它所在的网格列区间 (left, right)。"""
    if not bounds:
        return None
    t, x, xw, r = token
    if name == "数量" and "单位" in t:      # 「单位数量」合并 token → 数量在右半
        thr = x + (xw - x) * 0.45
        lefts = [b for b in bounds if b >= thr]
        left = min(lefts) if lefts else bounds[-1]
    else:
        c = (x + xw) // 2
        lefts = [b for b in bounds if b <= c]
        left = max(lefts) if lefts else bounds[0]
    rights = [b for b in bounds if b > left]
    right = min(rights) if rights else bounds[-1]
    if right - left < 20:
        return None
    return left, right


def col_center(img, hits, name):
    """按当前视图实测某列中心 x（name 可为 物料/类别/说明/数量/价格/需要日期）。"""
    bounds = _grid_bounds(to_bgr(img))
    for tok in view_cols(hits):
        if name in tok[0]:
            seg = _seg_for(bounds, tok, name)
            if seg:
                return (seg[0] + seg[1]) // 2
    return None


def col_seg(img, hits, name):
    bounds = _grid_bounds(to_bgr(img))
    for tok in view_cols(hits):
        if name in tok[0]:
            return _seg_for(bounds, tok, name)
    return None


def row1_y_from(hits):
    """行1中心 y：编号表头下沿 + 12。"""
    h = find_tok(hits, "编号", y_min=GRID_Y0, y_max=395, exact=True)
    if h:
        r = h[2]
        return int(r.y + r.h + 12)
    return 410


def focus_grid(app, y):
    """把焦点放进表格（点一个可编辑数据格），供 Tab / Shift+Tab 滚动用。"""
    img, hits = look(app)
    for name in ("类别", "价格", "说明", "编号"):
        cx = col_center(img, hits, name)
        if cx:
            click_at(app, cx, y, "表格")
            time.sleep(0.4)
            return True
    return False


def _view_ok(hits, want):
    txt = " ".join(t for t, _, _, _ in view_cols(hits))
    if want == "left":
        return "物料" in txt
    return "需要日期" in txt


def _scrollbar_y(hits):
    """表格横向滚动条的 y：紧贴「目的地类型」上方约 35px。"""
    d = find_tok(hits, "目的地类型", y_min=560)
    if d:
        return int(d[2].y - 35)
    return 588


def scroll_drag(app, x_to, y):
    """按住滚动条轨道拖动（实测：Tab/箭头都不可靠，拖拽最稳）。"""
    from pywinauto import mouse
    erp_ui.focus_window(app, settle=0.3)
    mouse.move(coords=(300, y))
    mouse.press(button="left", coords=(300, y))
    time.sleep(0.2)
    mouse.move(coords=(x_to, y))
    time.sleep(0.4)
    mouse.release(button="left", coords=(x_to, y))
    time.sleep(1.0)


def ensure_view(app, want, y=410):
    """want='left' → 露出「物料」；want='right' → 露出「需要日期」。

    做法：先拖到最左，再按固定档位往右拖，每档 OCR 表头确认。
    """
    img, hits = look(app)
    if _view_ok(hits, want):
        return img, hits
    sby = _scrollbar_y(hits)
    scroll_drag(app, 80, sby)                # 先回最左
    img, hits = look(app)
    if _view_ok(hits, want):
        return img, hits
    if want == "left":
        log("[WARN] 已拖到最左仍看不到「物料」")
        return img, hits
    for xt in (460, 520, 580, 640, 700):
        scroll_drag(app, xt, sby)
        img, hits = look(app)
        if _view_ok(hits, want):
            log(f"[INFO] 横向滚动条已拖到 x={xt}（right 视图就绪）")
            return img, hits
    log("[WARN] 滚动条拖到最右档仍未出现「需要日期」；当前表头="
        + " | ".join(t for t, _, _, _ in view_cols(hits)))
    return img, hits


def layout_right(img, hits):
    """在右视图构造 verify_doc 需要的 lay（列带用网格实测，避免旧缓存）。"""
    lay = layout_from(hits) or {}
    bgr = to_bgr(img)
    q = col_seg(img, hits, "数量")
    p = col_seg(img, hits, "价格")
    d = col_seg(img, hits, "需要日期")
    if q:
        lay["q_band"] = (q[0] + 3, q[1] - 3)
    if p:
        lay["p_band"] = (p[0] + 3, p[1] - 3)
    if d:
        lay["d_band"] = (d[0], d[1])
    lay["row1_y"] = row1_y_from(hits)
    hd = find_tok(hits, "说明", y_min=GRID_Y0, y_max=GRID_Y1, exact=True)
    if hd:
        lay["h_desc"] = hd[2]
    hdr = find_tok(hits, "说明", y_max=330, exact=True)
    if hdr:
        lay["hdr_desc"] = hdr[2]
    ix = col_center(img, hits, "物料")
    if ix:
        lay["item_x"] = ix
    cx = col_center(img, hits, "类别")
    if cx:
        lay["cat_x"] = cx
    return lay


# =====================================================================
# 校验（纯函数，可由 --self-test 离线调用）
# =====================================================================
#: 表头「说明」字段的纵向区间（实测标签 y≈207 h≈28）
HDR_DESC_Y = (185, 265)


def header_desc_hit(hits, desc, desc_core):
    """表头「说明」是否已填入期望文字，返回命中的 token 或 False。

    不依赖「说明」标签能否被 OCR 单独识别：实测 OCR 经常把标签和值粘成
    一条（如『说明采购订单失效补录』），按标签找字段就会误判为「未找到」。
    """
    for t, s, r in hits:
        if not (HDR_DESC_Y[0] <= r.y <= HDR_DESC_Y[1]):
            continue
        tt = t.strip()
        if tt in ("说明", "说明:", "说明："):
            continue
        if desc and desc in tt:
            return tt
        if desc_core and desc_core in tt:
            return tt
    return False


def verify_doc(img, hits, lay, doc, cfg, row_ys):
    rep = {}
    if img is None:
        rep["表单"] = (False, "截图失败，无法校验")
        return False, rep
    bgr = to_bgr(img)
    hdesc = lay["h_desc"]

    for i, (line, y) in enumerate(zip(doc["lines"], row_ys)):
        pre = f"行{i + 1}·"
        # 物料：以 EBS 自动带出的行说明为证据
        row_desc = [tx for tx, sc, r in hits
                    if y - 22 <= r.y <= y + 16 and r.x >= hdesc.x - 20
                    and len(tx.strip()) >= 5
                    and not tx.strip().replace(".", "").isdigit()]
        rep[pre + "物料"] = (bool(row_desc), row_desc[0] if row_desc else "行说明为空")
        # 数量 / 价格：优先 OCR 精确匹配（空格/粘连不会误判），读不到再退回像素
        for key, val, bk in (("数量", line["qty"], "q_band"),
                             ("价格", line["price"], "p_band")):
            band = lay[bk]
            want = norm_digits(val)
            got = [tx for tx, sc, r in hits
                   if y - 22 <= r.y <= y + 16
                   and band[0] - 20 <= (r.x + r.w // 2) <= band[1] + 20
                   and norm_digits(tx) == want]
            if got:
                rep[pre + key] = (True, f"{val}（OCR={got[0]}）")
            else:
                ok, st = numeric_cell_filled(bgr, band, y, val)
                rep[pre + key] = (ok, f"{val}（占位={st[0]:.4f} 位数={st[1]}/{st[2]}）")
        # 需要日期
        want = norm_digits(line["date"])
        got = [tx for tx, sc, r in hits
               if y - 22 <= r.y <= y + 16 and want in norm_digits(tx)]
        rep[pre + "需要日期"] = (bool(got), got[0] if got else "空")

    # 表头说明
    lab = lay.get("hdr_desc")
    if lab is not None:
        got = [tx for tx, sc, r in hits
               if r.x >= lab.x + lab.w - 20 and lab.y - 14 <= r.y <= lab.y + lab.h + 18
               and (doc["desc"] in tx or cfg["desc_core"] in tx)]
    else:
        got = []
    if not got:
        hit = header_desc_hit(hits, doc["desc"], cfg["desc_core"])
        got = [hit] if hit else []
    rep["说明"] = (bool(got), got[0] if got else "空")

    # 组织 / 地点 / 子库存
    dest = find_tok(hits, "目的地类型", y_min=560)
    if dest:
        cy = dest[2].y + dest[2].h // 2
        bands = {"组织": (cy + 45, cy + 88),
                 "地点": (cy + 88, cy + 128),
                 "子库存": (cy + 118, cy + 178)}
    else:
        bands = {"组织": (660, 722), "地点": (722, 760), "子库存": (752, 810)}
    for name, key in (("组织", cfg["org"][:3]), ("地点", cfg["loc"][:3])):
        b = bands[name]
        got = [tx for tx, sc, r in hits if b[0] <= r.y <= b[1] and key in tx and r.x < 520]
        rep[name] = (bool(got), got[0] if got else "空")
    b = bands["子库存"]
    got = [tx for tx, sc, r in hits
           if b[0] <= r.y <= b[1] and norm_code(cfg["subinv"]) in norm_code(tx)]
    rep["子库存"] = (bool(got), got[0] if got else "空")

    return all(v[0] for v in rep.values()), rep


def print_report(rep):
    for k, (ok, detail) in rep.items():
        log(f"   {'[OK]  ' if ok else '[缺失]'} {k}: {detail}")


# =====================================================================
# 录入
# =====================================================================
def fill_item_at(app, lay, row_y, item, tag=""):
    """在某一行录入物料，以「行说明被自动带出」为成功依据。"""
    x = lay.get("item_x") or lay.get("cat_x")
    if not x:
        return False
    for attempt in range(3):
        click_at(app, x, row_y, f"{tag}物料")
        time.sleep(0.4)
        clear_field(app, 20)
        type_in(app, item)
        time.sleep(3.0)
        img, hits = look(app)
        err = dialog_is_error(hits, row_y - 240, row_y + 140)
        if err:
            log(f"[FAIL] 物料 {item} 校验报错：{err}")
            return False
        dismiss_dialogs(app)
        img, hits = look(app)
        row_desc = [tx for tx, sc, r in hits
                    if row_y - 22 <= r.y <= row_y + 16
                    and r.x >= lay["h_desc"].x - 20
                    and len(tx.strip()) >= 5
                    and not tx.strip().replace(".", "").isdigit()]
        if row_desc:
            log(f"[OK] {tag}物料 {item} → {row_desc[0]}")
            return True
        log(f"[RETRY] {tag}物料 {item} 第{attempt + 1}次未见带出说明")
        time.sleep(1.0)
    return False


def fill_cell_number(app, lay, band, row_y, value, tag):
    for attempt in range(3):
        click_at(app, (band[0] + band[1]) // 2, row_y, tag)
        time.sleep(0.3)
        clear_field(app, 14)
        type_in(app, value)
        time.sleep(0.9)
        img = grab(app)
        if img is None:
            continue
        ok, st = numeric_cell_filled(to_bgr(img), band, row_y, value)
        if ok:
            log(f"[OK] {tag} → {value}（位数 {st[1]}/{st[2]}）")
            return True
        log(f"[RETRY] {tag} 第{attempt + 1}次（占位={st[0]:.4f} 位数={st[1]}/{st[2]}）")
    return False


def fill_cell_date(app, lay, row_y, date_s, tag):
    hd = lay["h_date"]
    for attempt in range(3):
        click_at(app, hd.x + hd.w // 2, row_y, tag)
        time.sleep(0.3)
        clear_field(app, 24)
        type_in(app, date_s)
        time.sleep(0.9)
        img, hits = look(app)
        want = norm_digits(date_s)
        got = [tx for tx, sc, r in hits
               if lay["d_band"][0] <= r.x <= lay["d_band"][1]
               and row_y - 22 <= r.y <= row_y + 16
               and want in norm_digits(tx)]
        if got:
            log(f"[OK] {tag} → {got[0]}")
            return True
        log(f"[RETRY] {tag} 第{attempt + 1}次")
    return False


HDR_DESC_FALLBACK = (247, 221)       # 标签 Rect≈(158,207,49,28) 时实测可命中的落点


def fill_header_desc(app, lay, desc, desc_core):
    lab = lay.get("hdr_desc")
    pts = []
    if lab is not None:
        pts += [(lab.x + lab.w + 40, lab.y + lab.h // 2),
                (lab.x + lab.w + 120, lab.y + lab.h // 2)]
    pts.append(HDR_DESC_FALLBACK)
    for attempt, (px, py) in enumerate(pts, 1):
        click_at(app, px, py, "表头说明")
        time.sleep(0.35)
        clear_field(app, 50)
        type_in(app, desc)
        time.sleep(0.9)
        img, hits = look(app)
        got = header_desc_hit(hits, desc, desc_core)
        if got:
            log(f"[OK] 表头说明 → {got}")
            return True
        log(f"[RETRY] 表头说明 第{attempt}次未确认（落点 {px},{py}）")
    return False


def bottom_rows(hits, fallback_cy):
    dest = find_tok(hits, "目的地类型", y_min=560)
    if dest:
        cy = dest[2].y + dest[2].h // 2
        x = int(dest[2].x + dest[2].w + 90)
    else:
        cy, x = fallback_cy, 320
    return {"组织": cy + 69, "地点": cy + 109, "子库存": cy + 143}, x


_FIELD_LABELS = {"组织", "地点", "子库存", "申请人", "来源", "供应商",
                 "目的地类型", "最终收货组织", "库存"}


def _field_has_value(hits, x_field, y, key, label=None):
    """字段区域里是否出现期望值；返回命中的文字或 False。

    OCR 常把「标签+值」粘成一个 token（如『子库存WL301』），
    所以以 label 开头的合并 token 也认。
    """
    for t, s, r in hits:
        if not (y - 18 <= r.y <= y + 18):
            continue
        tt = t.strip()
        merged = bool(label) and tt.startswith(label) and len(tt) > len(label)
        if not merged and (r.x < x_field - 120 or r.x > x_field + 420):
            continue
        if tt in _FIELD_LABELS:
            continue
        if key in t or key in norm_code(t):
            return t
    return False


def lov_is_open(hits, y):
    """LOV 弹窗是否打开：字段下方出现「名称+代码」表头，或「查找」按钮。"""
    below = " ".join(t for t, s, r in hits if r.y > y + 15)
    if "名称" in below and "代码" in below:
        return True
    return any(t.strip() == "查找" and r.y > y + 15 for t, s, r in hits)


def lov_pick(app, hits, key, y):
    """在 LOV 列表里点匹配行 → 确定 → 等弹窗关闭。"""
    rows = [(t, r) for t, s, r in hits
            if r.y > y + 15 and r.x < 800
            and (key in t or key in norm_code(t))
            and t.strip() not in ("名称", "代码", "查找")]
    if not rows:
        return False
    rows.sort(key=lambda z: z[1].y)
    t, r = rows[0]
    log(f"[LOV] 选「{t}」{r.center}")
    erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
    time.sleep(0.6)
    btn = None
    for tt, ss, rr in hits:
        if tt.strip() == "确定" and rr.y > y + 15:
            btn = rr
    if btn is not None:
        erp_ui.click_rect(app, btn, dx=0.5, dy=0.5)
    else:
        app.window.type_keys("{ENTER}")
    # 等弹窗真正关闭（最多 6s）
    for _ in range(6):
        time.sleep(1.0)
        img2, hits2 = look(app)
        if not lov_is_open(hits2, y):
            return True
    return True


def lov_cancel(app, hits, y):
    """关掉 LOV（取消），避免后续输入落到弹窗里。"""
    for t, s, r in hits:
        if t.strip() == "取消" and r.y > y:
            erp_ui.click_rect(app, r, dx=0.5, dy=0.5)
            time.sleep(1.0)
            return True
    app.window.type_keys("{ESC}")
    time.sleep(1.0)
    return False


def _wait_after_tab(app, x_field, y, key, label, timeout=12.0):
    """Tab 提交后轮询等待：LOV 弹窗（Java 弹窗有 1~4s 延迟）或字段已带值。

    LOV 必须优先判定：弹窗开着时字段值一定是空的/不可信的。
    返回 (img, hits, lov_opened)。
    """
    t0 = time.time()
    img, hits = look(app)
    while time.time() - t0 < timeout:
        if lov_is_open(hits, y):
            return img, hits, True
        if _field_has_value(hits, x_field, y, key, label):
            return img, hits, False
        time.sleep(1.0)
        img, hits = look(app)
    return img, hits, lov_is_open(hits, y)


def fill_bottom(app, field, value, rows, x_field, check_key):
    """填底部 LOV 字段。关键：按 Tab 后 LOV 可能延迟弹出，必须轮询到并选行确认。"""
    y = rows[field]
    for attempt in range(1, 4):
        click_at(app, x_field, y, field, w=90)
        time.sleep(0.3)
        clear_field(app, 20)
        type_in(app, value)
        time.sleep(0.8)
        app.window.type_keys("{TAB}")
        img, hits, lov = _wait_after_tab(app, x_field, y, check_key, field)

        if lov:
            log(f"[LOV] {field} 弹出列表，选「{check_key}」")
            if not lov_pick(app, hits, check_key, y):
                lov_cancel(app, hits, y)
                log(f"[RETRY] {field} 第{attempt}次：LOV 列表无「{check_key}」")
                continue
            img, hits = look(app)
            if lov_is_open(hits, y):
                lov_cancel(app, hits, y)
                log(f"[RETRY] {field} 第{attempt}次：选完 LOV 仍未关闭")
                continue
            got = _field_has_value(hits, x_field, y, check_key, field)
            if got:
                log(f"[OK] {field}(LOV) → {got}")
                return True
            log(f"[RETRY] {field} 第{attempt}次：LOV 选完字段仍为空")
            continue

        got = _field_has_value(hits, x_field, y, check_key, field)
        if got:
            log(f"[OK] {field} → {got}")
            return True
        log(f"[RETRY] {field} 第{attempt}次：字段未确认且无 LOV")
    return False


def _cell_text_ok(hits, y, seg, value, date=False):
    """OCR 复核：行 y、列区间 seg 内出现期望值。返回命中的文字或 None。

    用「列区间」而不是「列中心」：数值是左对齐/短文本（如价格 0 贴着列左沿）。
    """
    want = norm_digits(value)
    if not want:
        return None
    for t, s, r in hits:
        if not (y - 24 <= r.y <= y + 18):
            continue
        c = r.x + r.w // 2
        if not (seg[0] - 30 <= c <= seg[1] + 30):
            continue
        got = norm_digits(t)
        if not got:
            continue
        if date:
            if len(got) >= 6 and (got in want or want in got):
                return t
        elif got == want:
            return t
    return None


def fill_one_line(app, y, line, tag):
    """录一行：物料（左视图）→ 数量/价格/需要日期（右视图），每步 OCR 复核。"""
    # ① 物料：必须在左视图（物料列可见），点列中心，输完 Tab 触发校验
    img, hits = ensure_view(app, "left", y)
    cx = col_center(img, hits, "物料")
    if cx is None:
        log(f"[FAIL] {tag}左视图找不到「物料」列")
        return False
    got_desc = None
    for attempt in range(1, 4):
        click_at(app, cx, y, tag + "物料")
        time.sleep(0.4)
        clear_field(app, 24)
        type_in(app, line["item"])
        time.sleep(0.5)
        app.window.type_keys("{TAB}")
        time.sleep(3.5)
        img, hits = look(app)
        err = dialog_is_error(hits, y - 260, y + 200)
        if err:
            log(f"[FAIL] {tag}物料 {line['item']} 校验报错：{err}")
            return False
        dismiss_dialogs(app)
        img, hits = look(app)
        # 证据：该行「说明」被自动带出（排除纯数字/物料号）
        d_cx = col_center(img, hits, "说明") or 700
        cand = [t for t, s, r in hits
                if y - 22 <= r.y <= y + 16
                and r.x >= d_cx - 150
                and len(t.strip()) >= 5
                and not t.strip().replace(".", "").replace(" ", "").isdigit()]
        if cand:
            got_desc = cand[0]
            log(f"[OK] {tag}物料 {line['item']} → {got_desc}")
            break
        log(f"[RETRY] {tag}物料 第{attempt}次未见带出说明")
        time.sleep(1.0)
    if got_desc is None:
        return False

    # ② 数量 / 价格 / 需要日期：滚到右视图，按实测列中心逐个点填
    img, hits = ensure_view(app, "right", y)
    for name, value in (("数量", line["qty"]),
                        ("价格", line["price"]),
                        ("需要日期", line["date"])):
        seg = col_seg(img, hits, name)
        cx = col_center(img, hits, name)
        if seg is None or cx is None:
            log(f"[FAIL] {tag}右视图找不到「{name}」列")
            return False
        ok = False
        for attempt in range(1, 4):
            click_at(app, cx, y, tag + name)
            time.sleep(0.3)
            clear_field(app, 22)
            type_in(app, value)
            time.sleep(0.8)
            img2, hits2 = look(app)
            err = dialog_is_error(hits2, y - 260, y + 200)
            if err:
                log(f"[FAIL] {tag}{name} 校验报错：{err}")
                return False
            hit = _cell_text_ok(hits2, y, seg, value, date=(name == "需要日期"))
            if not hit and name in ("数量", "价格"):
                ink, ratio, cnt = _cell_has_ink(img2, seg, y)
                if ink:
                    hit = f"像素(占比={ratio:.4f} 位数={cnt})"
            if hit:
                ok = True
                log(f"[OK] {tag}{name} → {value}  [{hit}]")
                img, hits = img2, hits2
                break
            log(f"[RETRY] {tag}{name} 第{attempt}次未读回")
            seg2 = col_seg(img2, hits2, name)
            if seg2:
                seg = seg2
            cx2 = col_center(img2, hits2, name)
            if cx2:
                cx = cx2
            img, hits = img2, hits2
            time.sleep(0.6)
        if not ok:
            return False
    return True


def _cell_has_ink(img, seg, y):
    """单元格是否已有内容（OCR 会漏识别单独的 0，用像素兜底）。

    注意：单个「0」是带孔椭圆，连通域统计会得到 0 个，所以只看墨迹占比。
    """
    bgr = to_bgr(img)
    ratio, cnt = cell_stats(bgr, seg[0] + 4, y - 17, seg[1] - 4, y + 15)
    return ratio > 0.0015, ratio, cnt


def _row_number_at(hits, y):
    """读 编号 列在 y 附近显示的行号。"""
    for t, s, r in hits:
        if 78 <= r.x <= 150 and abs((r.y + r.h // 2) - y) <= 18:
            d = norm_digits(t)
            if d:
                return d
    return None


def create_next_line(app, prev_y):
    """用「编号行按 ↓」新建下一条记录（实测：鼠标点空行无效）。"""
    img, hits = look(app)
    num_cx = col_center(img, hits, "编号") or 106
    step = detect_row_step(to_bgr(img), prev_y) or DEFAULT_ROW_STEP
    new_y = prev_y + step
    for attempt in range(3):
        click_at(app, num_cx, prev_y, "编号")
        time.sleep(0.5)
        app.window.type_keys("{DOWN}")
        time.sleep(1.4)
        img, hits = look(app)
        got = _row_number_at(hits, new_y)
        if got and got != "1":
            log(f"[OK] 已新建行 编号={got}  y={new_y}")
            return new_y
        log(f"[RETRY] 新建行 第{attempt + 1}次未确认（编号={got}）")
    log("[WARN] 未确认新建行，按实测行高继续")
    return new_y


def bottom_state(app, cfg):
    """读回 组织/地点/子库存 当前是否已填对（用于「改表头后被重置」的复核）。"""
    img, hits = look(app)
    rows, x_field = bottom_rows(hits, 640)
    st = {
        "组织": _field_has_value(hits, x_field, rows["组织"], cfg["org"][:3], "组织"),
        "地点": _field_has_value(hits, x_field, rows["地点"], cfg["loc"][:3], "地点"),
        "子库存": _field_has_value(hits, x_field, rows["子库存"],
                                   norm_code(cfg["subinv"]), "子库存"),
    }
    return st, rows, x_field


def fill_doc(app, doc, cfg):
    """录入一整张单。顺序（实测业务约束，不能颠倒）：
       第1行 → 表头说明 → 组织/地点/子库存 → 用 ↓ 新建后续行逐行录。

    ⚠️ 表头说明若放在组织/地点/子库存之后填，提交表头会把底部三项重置回
       默认值（SANYO.科学大道工厂），所以表头说明必须排在底部字段之前。
    ⚠️ 表头说明又必须在「当前记录字段完整」之后才能点进去（否则 Forms 禁止切块）。
    返回 (ok, lay, row_ys)。"""
    lines = doc["lines"]
    img, hits = ensure_view(app, "left", 410)
    if not any("物料" in t for t, _, _, _ in view_cols(hits)):
        save_shot(img, os.path.join(LOGS, "form_layout_probe.png"))
        log("[FAIL] 未进入申请-[新建]（看不到『物料』列）")
        return False, None, []
    row1 = row1_y_from(hits)
    step = detect_row_step(to_bgr(img), row1)
    row_ys = [row1 + i * step for i in range(len(lines))]
    log(f"[INFO] 行高={step}px  行中心={row_ys}")

    # ① 第 1 行
    if not fill_one_line(app, row_ys[0], lines[0], "行1·"):
        return False, None, row_ys

    # ② 表头说明（第 1 行已完整 + 无 LOV 才能切到表头块）
    img, hits = look(app)
    num_cx = col_center(img, hits, "编号") or 106
    click_at(app, num_cx, row_ys[0], "编号(提交行1)")
    time.sleep(0.8)
    img, hits = look(app)
    if not fill_header_desc(app, layout_right(img, hits), doc["desc"], cfg["desc_core"]):
        log("[FAIL] 表头说明未确认，停止（不保存）")
        return False, None, row_ys

    # ③ 组织 / 地点 / 子库存
    _, hits = look(app)
    rows, x_field = bottom_rows(hits, row_ys[0] + 224)
    ok_org = fill_bottom(app, "组织", cfg["org"], rows, x_field, cfg["org"][:3])
    ok_loc = fill_bottom(app, "地点", cfg["loc"], rows, x_field, cfg["loc"][:3])
    ok_sub = fill_bottom(app, "子库存", cfg["subinv"], rows, x_field,
                         norm_code(cfg["subinv"]))
    if not (ok_org and ok_loc and ok_sub):
        log("[FAIL] 组织/地点/子库存 未全部确认，停止（不录后续行）")
        return False, None, row_ys

    # ④ 后续行：用 ↓ 新建记录
    for i in range(1, len(lines)):
        y = create_next_line(app, row_ys[i - 1])
        row_ys[i] = y
        if not fill_one_line(app, y, lines[i], f"行{i + 1}·"):
            return False, None, row_ys

    # ⑤ 底部三项复核：若被后续行提交重置，就地补填（此时不会再有表头提交）
    st, rows, x_field = bottom_state(app, cfg)
    lost = [k for k, v in st.items() if not v]
    if lost:
        log(f"[WARN] 录完后续行后底部字段被重置：{lost}，就地补填")
        vals = {"组织": cfg["org"], "地点": cfg["loc"], "子库存": cfg["subinv"]}
        keys = {"组织": cfg["org"][:3], "地点": cfg["loc"][:3],
                "子库存": norm_code(cfg["subinv"])}
        rows, x_field = bottom_rows(look(app)[1], row_ys[0] + 224)
        for k in lost:
            fill_bottom(app, k, vals[k], rows, x_field, keys[k])

    img, hits = look(app)
    return True, layout_right(img, hits), row_ys


# =====================================================================
# 导航 / 打开申请表单
# =====================================================================
def close_form_window(hwnd):
    """温和关闭一张单的 applet 窗口（只发 WM_CLOSE，不杀 java 进程，
    防止多个 applet 共享 JVM 时误伤）。关不掉也不影响后续流程。"""
    try:
        import win32con
        import win32gui
        hwnd = int(hwnd)
        if not win32gui.IsWindow(hwnd):
            return
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
        time.sleep(2.0)
    except Exception as e:
        log(f"[WARN] 关窗异常: {e}")


def wait_new_forms(before, timeout=150):
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(3)
        for hwnd, title in erp_navigator.snapshot_forms_windows().items():
            if hwnd not in before:
                return hwnd, title
    return None, None


def scroll_to_grid_header(app, max_tabs=15):
    """表格列超出可视区时（数量/价格/需要日期 在右侧不可见），
    点进表格后按 TAB 横向滚动，直到 layout_from 成功。

    ⚠️ 实测：表单默认停在最左列（编号/类型/物料/版本类别/说明/单位），
       需要 TAB 滚动若干次才会出现 数量/价格/需要日期。
    """
    img, hits = look(app)
    lay = layout_from(hits)
    if lay is not None:
        return img, hits, lay
    click_at(app, 620, 440, "表格", w=140, h=24)   # 点数据区，确保焦点在表格
    time.sleep(0.6)
    for i in range(1, max_tabs + 1):
        app.window.type_keys("{TAB}")
        time.sleep(0.6)
        img, hits = look(app)
        lay = layout_from(hits)
        if lay is not None:
            log(f"[INFO] 表格已横向滚动 {i} 次，数量/价格/需要日期 已可见")
            return img, hits, lay
    return img, hits, None


def wait_org_ready(app, timeout=200, poll=3.0):
    """等 applet 把「更改组织」表单真正画出来。

    判据：OCR 能认出「更改组织 / 常用表单 / 打开(Q)」之一。
    javaws 起来时窗口会先出现一张 ORACLE 启动图（空白页），此时任何点击都无效，
    直接去点工厂行只会白等 45s 然后误判失败。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        img, hits = look(app, focus=True)
        txt = " ".join(t for t, s, r in hits)
        if ("更改组织" in txt or "常用表单" in txt
                or find_tok(hits, "打开") is not None):
            log(f"[INFO] 更改组织表单已就绪（{int(time.time() - t0)}s）")
            return img, hits
        time.sleep(poll)
    save_shot(img, os.path.join(LOGS, "org_not_ready.png"))
    return None, []


def forms_ready(app, timeout=90):
    """等 applet 真正把表单网格画出来（否则抓到的是导航页/桌面）。

    判据：layout_from 能识别出行网格表头（说明/数量/价格/需要日期）。
    导航页虽有「常用表单/申请/组织」，但没有网格表头，不会被误判。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        img, hits = look(app, focus=True)
        if hits and layout_from(hits) is not None:
            return img, hits
        time.sleep(2.0)
    return None, []


def open_requisition(ie, cfg, tag=""):
    """完整开一张新申请单：职责 → 更改组织 → 工厂 → 2.申请 → 打开。"""
    log(f"[{tag}] 展开职责「{RESP}」")
    if not erp_navigator.expand_responsibility(ie, RESP):
        log(f"[FAIL] {tag} 职责展开失败")
        return None, None
    url = erp_navigator.read_function_url(ie, FUNC_ORG, resp_name=RESP)
    if not url:
        log(f"[FAIL] {tag} 未找到「{FUNC_ORG}」")
        return None, None

    before = erp_navigator.snapshot_forms_windows()
    ie2 = erp_navigator.open_forms_window(url)
    if ie2 is None:
        log(f"[FAIL] {tag} 承载窗口创建失败")
        return None, None
    ie2_hwnd = get_ie_hwnd(ie2, tries=3)
    if ie2_hwnd is None:
        new_frames = [h for h in ie_frame_hwnds()]
        if new_frames:
            ie2_hwnd = new_frames[-1]
        else:
            # 实测：IE 加载 Forms 后会自行退出，Java applet 窗口仍独立存活。
            # 后续全程只驱动 applet（截图/点击），所以 IE 窗口缺失不阻塞。
            log(f"[WARN] {tag} IE 窗口已退出（applet 仍会独立出现），继续等 applet")
    else:
        force_foreground(ie2_hwnd)
    hwnd, _title = wait_new_forms(before)
    if hwnd is None:
        log(f"[FAIL] {tag} 等待 Forms 窗口超时")
        return None, None

    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(hwnd):
        log(f"[FAIL] {tag} 连接 Forms 失败")
        return None, None
    force_foreground(hwnd)
    erp_ui.focus_window(app, settle=2.0)
    return drive_requisition(app, hwnd, cfg, tag)


def drive_requisition(app, hwnd, cfg, tag=""):
    """在已连上的「更改组织」applet 上继续：工厂 → 常用表单 2.申请 → 打开。

    IE 入口与 javaws 入口共用这一段（两条路拿到的都是 SunAwtFrame applet）。
    返回 (app, hwnd)。
    """
    img, hits = look(app, focus=True)
    # 组织变更窗口没有 requisition 网格，不等 forms_ready；
    # 但 javaws 起来时会先显示 ORACLE 启动图，必须等表单真的画出来
    if find_tok(hits, FACTORY) is None:
        img2, hits2 = wait_org_ready(app)
        if img2 is not None:
            img, hits = img2, hits2

    # 选工厂
    row = find_tok(hits, FACTORY, x_min=100, x_max=320)
    if row is None:
        lab = find_tok(hits, "组织", y_min=520, exact=True)
        if lab:
            click_at(app, lab[2].x + lab[2].w + 120, lab[2].y + lab[2].h // 2, "组织字段")
            time.sleep(2.0)
        t0 = time.time()
        while time.time() - t0 < 45 and row is None:
            img, hits = look(app, focus=True)
            row = find_tok(hits, FACTORY, x_min=100, x_max=320)
            if row is None:
                time.sleep(3.0)
    if row is None:
        save_shot(img, os.path.join(LOGS, "org_probe.png"))
        log(f"[FAIL] {tag} 工厂列表找不到「{FACTORY}」")
        return None, None
    click_at(app, row[2].center[0], row[2].center[1], FACTORY)
    time.sleep(0.8)
    okb = find_tok(look(app)[1], "确定", y_min=300)
    if okb is None:
        log(f"[FAIL] {tag} 工厂 LOV 无「确定」")
        return None, None
    erp_ui.click_rect(app, okb[2], dx=0.5, dy=0.5)
    time.sleep(2.5)

    # 常用表单 → 2.申请 → 打开
    item = None
    t0 = time.time()
    while time.time() - t0 < 40 and item is None:
        img, hits = look(app, focus=True)
        for t, s, r in hits:
            if t.strip().lstrip("0123456789.、． ") == WORD_APPLY and r.x > 380:
                item = (t, s, r)
        if item is None:
            time.sleep(2.0)
    if item is None:
        log(f"[FAIL] {tag} 常用表单无「2.申请」")
        return None, None
    erp_ui.click_rect(app, item[2], dx=0.5, dy=0.5)
    time.sleep(0.8)
    btn = find_tok(look(app)[1], "打开", y_min=450)
    if btn is None:
        log(f"[FAIL] {tag} 找不到「打开(O)」")
        return None, None
    erp_ui.click_rect(app, btn[2], dx=0.5, dy=0.5)
    time.sleep(6.0)
    dismiss_dialogs(app)                     # 「组织和地点不允许为空」

    # 打开可能复用本窗口，也可能新建 applet：逐个候选窗口试连，
    # 只有「截图尺寸正常 + OCR 认出申请表单」才认，避免连到隐藏窗口/桌面。
    time.sleep(1.5)
    dismiss_dialogs(app)
    app2, target, img, hits = None, None, None, []
    t0 = time.time()
    while time.time() - t0 < 75:
        snap = erp_navigator.snapshot_forms_windows()
        order = [h for h in snap if h != hwnd] + ([hwnd] if hwnd in snap else [])
        for h in order:
            cand = erp_forms.FormsApp()
            if not cand.connect_by_hwnd(h):
                continue
            force_foreground(h)
            im = grab(cand, focus=True)
            if im is None or im.width < 800 or im.height < 600:
                log(f"[INFO] {tag} 候选窗口 {h} 截图异常"
                    f"（{None if im is None else im.size}），跳过")
                continue
            hs = ocr_hits(im)
            txt = " ".join(t for t, s, r in hs)
            if any(k in txt for k in ("申请", "编号", "业务实体", "物料")):
                app2, target, img, hits = cand, h, im, hs
                log(f"[OK] {tag} 申请窗口已就绪 hwnd={h}")
                break
            log(f"[INFO] {tag} 候选窗口 {h} 还没画出申请表单（{txt[:30]}…）")
        if app2 is not None:
            break
        time.sleep(3)
    if app2 is None:
        log(f"[FAIL] {tag} 未找到申请表单窗口")
        return None, None
    # 表格列可能超出可视区 → TAB 横向滚动到 数量/价格/需要日期
    lay = layout_from(hits) if hits else None
    if lay is None:
        img, hits, lay = scroll_to_grid_header(app2)
    if lay is None:
        if img is not None:
            save_shot(img, os.path.join(LOGS, "apply_form_probe.png"))
        log(f"[FAIL] {tag} 未进入申请-[新建]（表格列未就绪）")
        for t, s, r in (hits or []):
            log(f"   {t!r} {r.center}")
        return None, None
    log(f"[OK] {tag} 已进入申请-[新建]  hwnd={target}")
    return app2, target


def open_requisition_retry(ie, cfg, tag, tries=2):
    """展开职责/打开表单偶发把 IE 的 DOM 点崩（RPC 服务器不可用），
    此时只能重开 IE 重试。失败一次不至于让整张单报废。"""
    for n in range(1, tries + 1):
        try:
            app, hwnd = open_requisition(ie, cfg, tag)
            if app is not None:
                return app, hwnd, ie
            log(f"[WARN] {tag} 第{n}次打开申请未成功")
        except erp_navigator.IeBroken as e:
            log(f"[WARN] {tag} 第{n}次点崩 IE：{e}")
        except Exception as e:
            log(f"[WARN] {tag} 第{n}次打开申请异常：{e}")
        if n == tries:
            break
        log(f"[INFO] 重开 IE 重试（{n + 1}/{tries}）")
        try:
            erp_ie11.close_all(logout=False)
        except Exception:
            pass
        time.sleep(4)
        ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
        if ie is None or not erp_ie11.is_logged_in(ie):
            log("[FAIL] 重试时 EBS 登录失败")
            break
    return None, None, ie


def open_requisition_attach(cfg, tag=""):
    """--resume：复用已经在桌面上的 applet（上一轮失败/中断留下的现场）。"""
    snap = erp_navigator.snapshot_forms_windows()
    if not snap:
        log(f"[FAIL] {tag} 桌面上没有可复用的 applet 窗口")
        return None, None, None
    for hwnd in snap:
        app = erp_forms.FormsApp()
        if not app.connect_by_hwnd(hwnd):
            continue
        force_foreground(hwnd)
        erp_ui.focus_window(app, settle=2.0)
        img, hits = look(app, focus=True)
        txt = " ".join(t for t, s, r in hits)
        if ("更改组织" in txt or "常用表单" in txt
                or find_tok(hits, FACTORY) is not None):
            log(f"[OK] {tag} 复用现有 applet hwnd={hwnd}")
            app2, hwnd2 = drive_requisition(app, hwnd, cfg, tag)
            return app2, hwnd2, None
        if len(txt.strip()) < 8:
            # 启动图阶段：给一次等待
            img2, hits2 = wait_org_ready(app, timeout=120)
            if img2 is not None:
                log(f"[OK] {tag} 复用现有 applet hwnd={hwnd}（等待后）")
                return (*drive_requisition(app, hwnd, cfg, tag), None)
        log(f"[INFO] {tag} 窗口 {hwnd} 不是更改组织表单（{txt[:30]}…），跳过")
    return None, None, None


def open_requisition_jws(cfg, tag=""):
    """javaws 入口：HTTP 登录 → JNLP 起 applet → 选工厂 → 2.申请 → 打开。

    返回 (app, hwnd, session)；失败 (None, None, session)。
    """
    log(f"[{tag}] 用 javaws 直接启动 Forms（不经浏览器）")
    sess = None
    try:
        sess = erp_jws.start()
    except Exception as e:
        log(f"[FAIL] {tag} javaws 启动失败：{e}")
        return None, None, sess
    if not sess.get("hwnd"):
        log(f"[FAIL] {tag} 等不到 applet 窗口")
        return None, None, sess

    hwnd = sess["hwnd"]
    app = erp_forms.FormsApp()
    if not app.connect_by_hwnd(hwnd):
        log(f"[FAIL] {tag} 连接 applet 失败 hwnd={hwnd}")
        return None, None, sess
    force_foreground(hwnd)
    erp_ui.focus_window(app, settle=2.0)
    app2, hwnd2 = drive_requisition(app, hwnd, cfg, tag)
    return app2, hwnd2, sess


# =====================================================================
# 保存 / 审批
# =====================================================================
def save_doc(app):
    log("[保存] Ctrl+S")
    erp_ui.focus_window(app, settle=0.5)
    app.window.type_keys("^s")
    time.sleep(3.5)
    n = dismiss_dialogs(app)
    log(f"[保存] 清理弹窗 {n} 个")
    img, hits = look(app)
    for t, s, r in hits:
        c = re.sub(r"\D", "", t)
        if len(c) >= 8 and r.y < 330:
            save_shot(img, os.path.join(LOGS, f"req_saved_{c}.png"))
            log(f"[SAVED] 申请编号 = {c}")
            return c, img
    save_shot(img, os.path.join(LOGS, "save_failed.png"))
    log("[FAIL] 未读回申请编号（可能保存被拦截）")
    for t, s, r in hits:
        if r.y < 340:
            log(f"   {t!r} {r.center}")
    return None, img


def approve_doc(app):
    log("[审批] 点「审批(A)...」")
    _, hits = look(app)
    abtn = find_tok(hits, "审批", y_min=700)
    if abtn is None:
        log("[WARN] 找不到「审批(A)...」")
        return False
    erp_ui.click_rect(app, abtn[2], dx=0.5, dy=0.5)
    time.sleep(2.2)

    img, hits = look(app)
    chk = find_tok(hits, "提交以供审批")
    okb = find_tok(hits, "确定", y_min=700)
    if chk is None or okb is None:
        save_shot(img, os.path.join(LOGS, "approve_probe.png"))
        log("[FAIL] 审批对话框未弹出")
        return False

    # 鼠标点击只取焦点，{SPACE} 才真正勾选；用像素判据确认状态
    for attempt in range(3):
        checked, dark = checkbox_checked(to_bgr(img), chk[2])
        log(f"[审批] 提交以供审批 当前={'已勾选' if checked else '未勾选'}（暗点={dark}）")
        if checked:
            break
        click_at(app, int(chk[2].x + chk[2].h * 0.35),
                 chk[2].y + chk[2].h // 2, "提交以供审批框", w=24, h=24)
        time.sleep(0.5)
        app.window.type_keys("{SPACE}")
        time.sleep(1.0)
        img, hits = look(app)
        chk2 = find_tok(hits, "提交以供审批")
        okb2 = find_tok(hits, "确定", y_min=700)
        if chk2 is None or okb2 is None:
            log("[FAIL] 勾选后对话框异常消失")
            return False
        chk, okb = chk2, okb2
        img = grab(app) or img

    checked, dark = checkbox_checked(to_bgr(img), chk[2])
    if not checked:
        save_shot(img, os.path.join(LOGS, "approve_unchecked.png"))
        log(f"[FAIL] 未能确认已勾选（暗点={dark}），不提交")
        return False
    log("[OK] 「提交以供审批(S)」已勾选")
    save_shot(img, os.path.join(LOGS, "approve_dialog.png"))

    erp_ui.click_rect(app, okb[2], dx=0.5, dy=0.5)
    time.sleep(2.5)
    d = dismiss_dialogs(app)
    log(f"[审批] 提交后确认弹窗 {d} 个")
    time.sleep(1.0)
    return True


# =====================================================================
# 主流程
# =====================================================================
def run(cfg):
    results = []
    failed = False
    mode = "attach" if cfg.get("resume") else (cfg.get("launch") or "javaws")

    if mode == "attach":
        log("=== 步骤 1：复用桌面上已有的 applet（--resume）===")
        ie = None
    elif mode == "javaws":
        log("=== 步骤 1：javaws 直启 Forms（HTTP 登录，不经浏览器）===")
        ie = None          # javaws 入口没有 IE；open_requisition_jws 自己登录
    else:
        log("=== 步骤 1：IE11 登录 EBS ===")
        ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
        if ie is None or not erp_ie11.is_logged_in(ie):
            log("[FAIL] EBS 登录失败")
            return 2
        log("[OK] 已登录")

    total = len(cfg["docs"])
    for idx, doc in enumerate(cfg["docs"], 1):
        tag = f"单{idx}/{total}"
        log("")
        log(f"══════ {tag}  说明={doc['desc']}  行数={len(doc['lines'])} ══════")
        if mode == "javaws":
            app, hwnd, sess = open_requisition_jws(cfg, tag)
            if sess:
                cfg["_sess"] = sess
        elif mode == "attach":
            app, hwnd, _ = open_requisition_attach(cfg, tag)
        else:
            app, hwnd, ie = open_requisition_retry(ie, cfg, tag)
        if app is None:
            results.append({"idx": idx, "desc": doc["desc"], "number": None,
                            "status": "打开申请失败"})
            cfg["keep_ie"] = True
            failed = True
            break

        ok, lay, row_ys = fill_doc(app, doc, cfg)
        if not ok:
            results.append({"idx": idx, "desc": doc["desc"], "number": None,
                            "status": "录入失败"})
            cfg["keep_ie"] = True
            failed = True
            break

        # 校验（fill_one_line 已逐字段 OCR 复核；此处只做整单复核，不再用旧坐标盲补）
        log(f"[{tag}] 校验录入完整性")
        img, hits = look(app)
        final_ok, rep = verify_doc(img, hits, lay, doc, cfg, row_ys)
        print_report(rep)
        if not final_ok:
            log(f"[{tag}] 缺失项：{[k for k, v in rep.items() if not v[0]]}")

        img, _hits = look(app)
        if not final_ok:
            save_shot(img, os.path.join(LOGS, "req_incomplete.png"))
            log(f"[ABORT] {tag} 校验未通过，不保存")
            results.append({"idx": idx, "desc": doc["desc"], "number": None,
                            "status": "校验未通过(未保存)"})
            cfg["keep_ie"] = True
            cfg["media"] = os.path.join(LOGS, "req_incomplete.png")
            failed = True
            break
        save_shot(img, os.path.join(LOGS, f"req_filled_{idx}.png"))
        log(f"[OK] {tag} 全部字段校验通过")

        if cfg["stop_before_save"]:
            log(f"[STOP] --stop-before-save：{tag} 已录入并校验，不保存")
            results.append({"idx": idx, "desc": doc["desc"], "number": None,
                            "status": "演练(未保存)"})
            cfg["media"] = os.path.join(LOGS, f"req_filled_{idx}.png")
            break

        number, _ = save_doc(app)
        if not number:
            results.append({"idx": idx, "desc": doc["desc"], "number": None,
                            "status": "保存失败"})
            cfg["keep_ie"] = True
            cfg["media"] = os.path.join(LOGS, "save_failed.png")
            failed = True
            break

        approved = approve_doc(app)
        img, hits = look(app)
        save_shot(img, os.path.join(LOGS, f"req_done_{number}.png"))
        cfg["media"] = os.path.join(LOGS, f"req_done_{number}.png")
        status = [t for t, s, r in hits
                  if any(k in t for k in ("未完成", "审批中", "已提交", "已批准"))]
        results.append({"idx": idx, "desc": doc["desc"], "number": number,
                        "status": ("已提交审批 " if approved else "已保存(审批未确认) ")
                                  + (" ".join(status) if status else "")})
        if not approved:
            cfg["keep_ie"] = True
            failed = True
            break

        # 释放该 applet 窗口，跑下一张（最后一张留着看结果）
        if idx < total:
            log(f"[清理] 关闭 {tag} 窗口 hwnd={hwnd}")
            close_form_window(hwnd)

    # 汇总
    log("")
    log("══════════ 执行汇总 ══════════")
    for r in results:
        log(f"  单{r['idx']}  编号={r['number'] or '-':<14} {r['status']}  | {r['desc']}")
    ok_all = (not failed) and len(results) == total and all(r["number"] for r in results)
    if cfg["stop_before_save"]:
        return 0 if not failed else 10     # 演练模式：录到就没白跑
    return 0 if ok_all else 10


# =====================================================================
# 参数
# =====================================================================
def parse_plan(args):
    """返回 docs=[{desc, lines:[{item,qty,price,date}]}]"""
    base_date = (datetime.date.today() + datetime.timedelta(days=args.days)).isoformat()
    docs = []

    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            raw = raw.get("docs") or raw.get("requests") or [raw]
        for d in raw:
            lines = []
            for ln in d.get("lines", []):
                lines.append({
                    "item": str(ln["item"]).strip(),
                    "qty": str(ln.get("qty", "1")).strip(),
                    "price": str(ln.get("price", args.price)).strip(),
                    "date": str(ln.get("date") or base_date).strip(),
                })
            docs.append({"desc": str(d.get("desc") or args.desc), "lines": lines})

    for spec in (args.req or []):
        desc, sep, body = spec.partition("|")
        if not sep:                       # 允许 --req 只给行、用默认说明
            body, desc = spec, args.desc
        lines = []
        for part in body.split(","):
            part = part.strip()
            if not part:
                continue
            f = [x.strip() for x in part.split(":")]
            lines.append({
                "item": f[0],
                "qty": f[1] if len(f) > 1 and f[1] else "1",
                "price": f[2] if len(f) > 2 and f[2] else args.price,
                "date": f[3] if len(f) > 3 and f[3] else base_date,
            })
        docs.append({"desc": desc.strip() or args.desc, "lines": lines})

    if not docs and args.item:
        docs = [{"desc": args.desc,
                 "lines": [{"item": args.item, "qty": str(args.qty or "1"),
                            "price": args.price, "date": base_date}]}]

    return [d for d in docs if d["lines"]]


def build_cfg(args):
    docs = parse_plan(args)
    # 表头说明的「核心词」用于 OCR 兜底匹配（OCR 常把标签和值粘在一起）。
    # 默认取说明末尾 4 个字，说明本身很短时取全文，不写死业务文案。
    core = getattr(args, "desc_core", None)
    if not core:
        d0 = docs[0]["desc"] if docs else (args.desc or "")
        core = d0[-4:] if len(d0) >= 4 else d0
    return {
        "docs": docs,
        "price": str(args.price).strip(),
        "desc_core": core,
        "org": args.org,
        "loc": args.loc,
        "subinv": args.subinv,
        "keep_ie": args.keep_ie,
        "stop_before_save": args.stop_before_save,
        "launch": getattr(args, "launch", "javaws"),
        "resume": getattr(args, "resume", False),
        "media": None,
    }


def self_test(path, args):
    """用历史截图离线校验 verify 逻辑，不连 ERP、不产生单据。"""
    from PIL import Image
    cfg = build_cfg(args)
    doc = cfg["docs"][0]
    img = Image.open(path).convert("RGB")
    hits = ocr_hits(img)
    lay = layout_from(hits)
    if lay is None:
        log("[自检] 未识别到行网格表头")
        return 1
    step = detect_row_step(to_bgr(img), lay["row1_y"])
    row_ys = [lay["row1_y"] + i * step for i in range(len(doc["lines"]))]
    log(f"[自检] {path}")
    log(f"[自检] 行高={step}px 行中心={row_ys} 说明={doc['desc']}")
    ok, rep = verify_doc(img, hits, lay, doc, cfg, row_ys)
    print_report(rep)
    log(f"[自检] 结论：{'全部通过' if ok else '存在缺失项（见上）'}")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(
        description="惠而浦 EBS 采购申请批量全流程（N行/单 + 多单）")
    ap.add_argument("--req", action="append", metavar="说明|物料:数量,物料:数量",
                    help="一张采购申请单；可重复传入=多张单")
    ap.add_argument("--plan", help="JSON 计划文件（支持每行单独价格/日期）")
    ap.add_argument("--item", help="单行简写：物料编码")
    ap.add_argument("--qty", default="1", help="单行简写：数量")
    ap.add_argument("--price", default="0", help="默认价格，默认 0")
    ap.add_argument("--desc", default="零头补录入库", help="默认表头说明")
    ap.add_argument("--desc-core", default=None,
                    help="表头说明的 OCR 兜底核心词（默认取说明末尾 4 字）")
    ap.add_argument("--days", type=int, default=7, help="需要日期=今天+N天，默认 7")
    ap.add_argument("--org", default="洗衣机三工厂", help="组织")
    ap.add_argument("--loc", default="洗衣机三工厂", help="地点")
    ap.add_argument("--subinv", default="WL301", help="子库存")
    ap.add_argument("--resume", action="store_true",
                    help="不重新登录/启动，直接复用桌面上已打开的 applet（失败后接着跑）")
    ap.add_argument("--keep-ie", action="store_true", help="完成后保留 IE 供复核")
    ap.add_argument("--launch", choices=("javaws", "ie"), default="javaws",
                    help="入口：javaws=HTTP 登录后直启 Forms（默认，Win11 可用）；"
                         "ie=走 IE11 + COM（仅老系统/备选）")
    ap.add_argument("--stop-before-save", action="store_true",
                    help="只录入并校验第一张单，不保存（演练）")
    ap.add_argument("--self-test", nargs="?",
                    const=os.path.join(LOGS, "req_final.png"), metavar="PNG",
                    help="离线校验 verify 逻辑（默认 logs/req_final.png）")
    ap.add_argument("--dry-run", action="store_true",
                    help="只解析并打印执行计划，不连接 ERP、不产生单据")
    ap.add_argument("--open-only", action="store_true",
                    help="只登录并打开申请表单就停（调试列位置用，不录入不保存）")
    args = ap.parse_args()

    if args.self_test:
        if not args.req and not args.plan and not args.item:
            args.item = "3012324101140"
            args.qty = "1"
        return self_test(args.self_test, args)

    cfg = build_cfg(args)
    if not cfg["docs"]:
        ap.error("没有可执行内容：用 --req / --plan / --item --qty 指定物料")

    log("执行计划：")
    for i, d in enumerate(cfg["docs"], 1):
        log(f"  单{i}  说明={d['desc']}  {len(d['lines'])} 行")
        for ln in d["lines"]:
            log(f"       {ln['item']} × {ln['qty']}  价格={ln['price']}  "
                f"需要日期={ln['date']}")
    log("")

    if args.dry_run:
        log("[dry-run] 仅解析计划，不连接 ERP、不产生单据")
        return 0

    if args.open_only:
        log("=== [open-only] 登录并打开申请表单 ===")
        if cfg["launch"] == "javaws":
            app, hwnd, sess = open_requisition_jws(cfg, "open-only")
            cfg["_sess"] = sess
        else:
            ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
            if ie is None or not erp_ie11.is_logged_in(ie):
                log("[FAIL] EBS 登录失败")
                return 2
            log("[OK] 已登录")
            app, hwnd = open_requisition(ie, cfg, "open-only")
        if app is None:
            log("[FAIL] 打开申请失败")
            return 1
        log(f"[OK] 已打开申请表单 hwnd={hwnd}，保留现场（不录入）")
        return 0

    rc = 2
    try:
        rc = run(cfg)
    except KeyboardInterrupt:
        log("\n[中断] 用户取消")
        rc = 130
    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"[FAIL] 未捕获异常: {e}")
        rc = 1
    finally:
        # 成功才自动收口；失败/中断保留现场，方便人工接手
        if rc == 0 and not cfg["keep_ie"]:
            log("\n=== 收口：注销 EBS + 关闭 IE / applet ===")
            try:
                if cfg.get("launch") == "javaws":
                    erp_jws.logout((cfg.get("_sess") or {}).get("session"))
                    for h in list(erp_navigator.snapshot_forms_windows()):
                        close_form_window(h)
                else:
                    erp_ie11.close_all(logout=True)
                log("[OK] 已注销并关闭")
            except Exception as e:
                log(f"[WARN] 收口异常: {e}")
        else:
            log("\n[保留现场] IE 未关闭；人工处理完后运行：")
            log("  E:/SKILLS/.venv/Scripts/python.exe scripts/erp_ops.py logout")
    log(f"[退出码] {rc}")
    if cfg.get("media"):
        print(f"MEDIA:{cfg['media']}", flush=True)
    return rc


if __name__ == "__main__":
    sys.exit(main())
