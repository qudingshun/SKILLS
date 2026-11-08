#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_ui - Oracle Forms（Java AWT）界面元素定位与点击

背景
====
Oracle Forms 窗口是 Java AWT 自绘控件（class=SunAwtFrame），对 UIA backend
只暴露 TitleBar，内部控件无法枚举——所以本模块走**图像识别**路线：

    截图(窗口图像) → 模板匹配定位控件 → 返回【相对窗口图像的矩形】
    → 点击时按窗口屏幕位置换算成绝对坐标 → 点击

为什么用"相对坐标"
=================
用户要求「按屏幕大小及位置不同自动识别按钮位置」。如果直接用绝对屏幕坐标，
换分辨率/换窗口位置就全废。本模块的所有定位结果都表达为**相对被截图像左上角
的像素坐标**，点击时用 `window.rectangle()` 实时换算：

    屏幕坐标 = 窗口左上角(实时读取) + 相对坐标

于是：窗口移动 → 自动跟随；分辨率变化 → 模板多尺度匹配仍然命中；
多显示器/负坐标 → 无关。

模板库
======
目录结构：
    assets/templates/<form_id>/<语义名>.png     控件模板（自动裁剪、去白边）
    assets/templates/<form_id>/meta.json        记录语义名/参考尺寸/缩放
form_id 用职责+功能名的稳定标识（见 erp_ui.form_id()）。

公开 API
========
    capture(app)                     -> PIL.Image   截取 Forms 窗口图像
    locate(app, name, form_id)      -> Rect|None   定位一个语义元素
    locate_all(app, form_id)        -> {name: Rect} 定位全部已登记元素
    click(app, name, form_id)       -> bool        定位并点击
    click_rect(app, rect)           -> bool        点击相对矩形
"""
import json
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Oracle Forms 是 32 位 Java 应用，pywinauto 会提示"应使用 32 位 Python"——
# 实测基础能力（置前/键盘/截图）不受影响，这里静音以免刷屏。
warnings.filterwarnings("ignore", message="32-bit application should be automated*")

import numpy as np  # noqa: E402

from erp_common import safe_print  # noqa: E402

# ── 路径 ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
TEMPLATE_ROOT = os.path.join(PROJECT_DIR, "assets", "templates")
META_NAME = "meta.json"

# 匹配参数
DEFAULT_THRESHOLD = 0.72      # 模板匹配置信度门槛
SCALES = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95,
          1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40)   # 多尺度（DPI 缩放自适应）
MIN_SIZE = 8                  # 模板/命中框最小边长（像素）


def enable_dpi_awareness():
    """
    让本进程感知 DPI（Per-Monitor v2）。
    否则窗口矩形是逻辑坐标、截图是物理像素，两者换算会整体错位。
    """
    if getattr(enable_dpi_awareness, "_done", False):
        return
    enable_dpi_awareness._done = True
    try:
        import ctypes
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2
        except Exception:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)        # PER_MONITOR_DPI_AWARE
    except Exception:
        pass


enable_dpi_awareness()


def _log(msg):
    safe_print(f"[UI] {msg}")


# ── 图像 IO（兼容中文/非 ASCII 路径）────────────────────────────────────
def imread_unicode(path: str, flags=None):
    """
    读图（支持中文路径）。
    OpenCV 的 imread/imwrite 在 Windows 上处理不了非 ASCII 路径，
    这里统一走 np.fromfile / tofile。
    """
    import cv2
    if flags is None:
        flags = cv2.IMREAD_UNCHANGED
    try:
        buf = np.fromfile(path, dtype=np.uint8)
        if buf.size == 0:
            return None
        return cv2.imdecode(buf, flags)
    except Exception:
        return None


def imwrite_unicode(path: str, arr) -> bool:
    """写图（支持中文路径）"""
    import cv2
    try:
        ext = os.path.splitext(path)[1] or ".png"
        ok, buf = cv2.imencode(ext, arr)
        if not ok:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        buf.tofile(path)
        return True
    except Exception:
        return False


# ── 矩形 ────────────────────────────────────────────────────────────────
class Rect:
    """相对窗口图像左上角的矩形（x, y, w, h）"""

    __slots__ = ("x", "y", "w", "h", "score", "name")

    def __init__(self, x, y, w, h, score=0.0, name=""):
        self.x = int(x)
        self.y = int(y)
        self.w = int(w)
        self.h = int(h)
        self.score = float(score)
        self.name = name

    @property
    def center(self):
        return (self.x + self.w // 2, self.y + self.h // 2)

    @property
    def box(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def as_dict(self):
        return {"name": self.name, "x": self.x, "y": self.y,
                "w": self.w, "h": self.h, "score": round(self.score, 4)}

    def __repr__(self):
        return (f"Rect({self.name!r}, x={self.x}, y={self.y}, "
                f"w={self.w}, h={self.h}, score={self.score:.3f})")


# ── 截图 ────────────────────────────────────────────────────────────────
def focus_window(app, settle: float = 0.8):
    """
    把 Forms 窗口提到前台并等它重绘。

    必须做：Windows 上被遮挡窗口的 BitBlt 截图会取到**遮挡者**的内容
    （实测被 Excel 挡住时截出来是 Excel，模板匹配必然失败）。
    """
    try:
        import win32gui
        hwnd = int(app.window.handle)
        win32gui.ShowWindow(hwnd, 9)          # SW_RESTORE
        try:
            win32gui.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            app.window.set_focus()
        except Exception:
            pass
        time.sleep(settle)
        return True
    except Exception as e:
        _log(f"置前窗口失败: {e}")
        return False


def capture(app, focus: bool = True):
    """
    截取 Forms 窗口图像（pywinauto），返回 PIL.Image。
    focus=True 时先把窗口提到前台（否则会截到遮挡窗口的内容）。
    失败返回 None。
    """
    if focus:
        focus_window(app)
    try:
        img = app.window.capture_as_image()
        if img is not None:
            return img
    except Exception as e:
        _log(f"截图失败（pywinauto）: {e}")
    # 兜底：PrintWindow 抓整个窗口
    try:
        import win32gui
        from PIL import Image
        hwnd = int(app.window.handle)
        l, t, r, b = win32gui.GetWindowRect(hwnd)
        w, h = max(1, r - l), max(1, b - t)
        import win32ui
        hwndDC = win32gui.GetWindowDC(hwnd)
        mfcDC = win32ui.CreateDCFromHandle(hwndDC)
        saveDC = mfcDC.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfcDC, w, h)
        saveDC.SelectObject(bmp)
        saveDC.BitBlt((0, 0), (w, h), mfcDC, (0, 0), win32con_SRCCOPY)
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        img = Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]), bits,
                               "raw", "BGRX", 0, 1)
        win32gui.DeleteObject(bmp.GetHandle())
        saveDC.DeleteDC()
        mfcDC.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwndDC)
        return img
    except Exception as e:
        _log(f"截图失败（PrintWindow）: {e}")
        return None


win32con_SRCCOPY = 0x00CC0020


def window_rect(app):
    """返回 Forms 窗口的屏幕矩形 (left, top, right, bottom)，失败返回 None"""
    try:
        r = app.window.rectangle()
        return (int(r.left), int(r.top), int(r.right), int(r.bottom))
    except Exception:
        return None


# ── 模板库 ──────────────────────────────────────────────────────────────
def form_id(responsibility: str, function: str = "") -> str:
    """把职责/功能名转成稳定的模板目录名（去掉非法字符）"""
    raw = f"{responsibility}__{function}".strip("_") or "default"
    bad = '<>:"/\\|?* '
    out = "".join("_" if c in bad else c for c in raw)
    return out.strip("_") or "default"


class TemplateStore:
    """模板库读写"""

    def __init__(self, root: str = TEMPLATE_ROOT):
        self.root = root

    def dir_for(self, form: str) -> str:
        return os.path.join(self.root, form)

    def exists(self, form: str) -> bool:
        d = self.dir_for(form)
        return os.path.isdir(d) and any(f.endswith(".png") for f in os.listdir(d))

    def list_forms(self):
        if not os.path.isdir(self.root):
            return []
        return sorted(d for d in os.listdir(self.root)
                      if os.path.isdir(os.path.join(self.root, d)))

    def templates(self, form: str) -> dict:
        """{语义名: 模板 png 路径}"""
        d = self.dir_for(form)
        out = {}
        if not os.path.isdir(d):
            return out
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".png"):
                out[os.path.splitext(f)[0]] = os.path.join(d, f)
        return out

    def meta(self, form: str) -> dict:
        p = os.path.join(self.dir_for(form), META_NAME)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_meta(self, form: str, meta: dict):
        d = self.dir_for(form)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, META_NAME), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def add_template(self, form: str, name: str, png_bytes_or_path,
                     ref_size=None, ref_rect=None, ref_image_size=None) -> str:
        """写入一个模板（自动去白边），返回路径"""
        import cv2
        d = self.dir_for(form)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{name}.png")
        arr = png_bytes_or_path
        if isinstance(arr, str):
            arr = imread_unicode(arr)
        elif isinstance(arr, bytes):
            arr = cv2.imdecode(np.frombuffer(arr, np.uint8), cv2.IMREAD_UNCHANGED)
        if arr is None:
            raise ValueError(f"无法解码模板图像: {name}")
        arr = trim_border(arr)
        if not imwrite_unicode(path, arr):
            raise IOError(f"模板写入失败: {path}")
        meta = self.meta(form)
        entry = {"file": f"{name}.png", "ref_size": list(ref_size or [])}
        if ref_rect:
            entry["ref_rect"] = [int(v) for v in ref_rect]
        if ref_image_size:
            entry["ref_image_size"] = [int(v) for v in ref_image_size]
        meta[name] = entry
        self.save_meta(form, meta)
        return path

    def roi_for(self, form: str, name: str, scene_size, margin: float = 0.8):
        """
        由模板 meta 推导搜索区域（ROI）。
        仅当截图尺寸与基准图一致时有效（尺寸变了说明缩放变了，全图搜更稳）。
        返回 (x0, y0, x1, y1) 或 None。
        """
        entry = (self.meta(form) or {}).get(name) or {}
        rect = entry.get("ref_rect")
        ref_img = entry.get("ref_image_size")
        if not rect or not ref_img:
            return None
        if tuple(int(v) for v in ref_img) != tuple(int(v) for v in scene_size):
            return None
        x, y, w, h = rect
        mx, my = int(w * margin), int(h * margin)
        x0, y0 = max(0, x - mx), max(0, y - my)
        x1 = min(scene_size[0], x + w + mx)
        y1 = min(scene_size[1], y + h + my)
        return (x0, y0, x1, y1)


def trim_border(arr, pad: int = 2, thresh: int = 245):
    """裁掉模板四周的纯白边（保留 pad 像素），让匹配更准"""
    import cv2
    if arr.ndim == 3:
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    else:
        gray = arr
    mask = gray < thresh
    if not mask.any():
        return arr
    ys, xs = np.where(mask)
    y0, y1 = max(0, ys.min() - pad), min(gray.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(gray.shape[1], xs.max() + pad + 1)
    if y1 <= y0 or x1 <= x0:
        return arr
    return arr[y0:y1, x0:x1]


# ── 匹配引擎 ────────────────────────────────────────────────────────────
def _match_once(gray_scene, gray_tpl):
    """返回 (score, x, y, w, h)"""
    import cv2
    if (gray_tpl.shape[0] > gray_scene.shape[0] or
            gray_tpl.shape[1] > gray_scene.shape[1]):
        return None
    res = cv2.matchTemplate(gray_scene, gray_tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    h, w = gray_tpl.shape[:2]
    return (float(max_val), int(max_loc[0]), int(max_loc[1]), int(w), int(h))


def match_template(scene_img, tpl_img, scales=SCALES, threshold=DEFAULT_THRESHOLD,
                  roi=None):
    """
    在 scene_img 中多尺度查找 tpl_img。
    roi: 可选，(x0, y0, x1, y1) 只在该区域搜索（区域提示，来自模板 meta）。
    返回 Rect（相对 scene 左上角）或 None。
    """
    import cv2
    if scene_img is None or tpl_img is None:
        return None
    if scene_img.ndim == 3:
        gray_scene = cv2.cvtColor(scene_img, cv2.COLOR_BGR2GRAY)
    else:
        gray_scene = scene_img
    if tpl_img.ndim == 3:
        gray_tpl0 = cv2.cvtColor(tpl_img, cv2.COLOR_BGR2GRAY)
    else:
        gray_tpl0 = tpl_img

    # 区域提示：裁出 ROI 单独匹配，最后把坐标加回偏移
    off_x = off_y = 0
    if roi:
        x0, y0, x1, y1 = roi
        x0 = max(0, int(x0)); y0 = max(0, int(y0))
        x1 = min(gray_scene.shape[1], int(x1)); y1 = min(gray_scene.shape[0], int(y1))
        if x1 - x0 > MIN_SIZE and y1 - y0 > MIN_SIZE:
            gray_scene = gray_scene[y0:y1, x0:x1]
            off_x, off_y = x0, y0

    best = None
    for s in scales:
        if s == 1.0:
            gt = gray_tpl0
        else:
            nw = max(MIN_SIZE, int(round(gray_tpl0.shape[1] * s)))
            nh = max(MIN_SIZE, int(round(gray_tpl0.shape[0] * s)))
            if nw > gray_scene.shape[1] or nh > gray_scene.shape[0]:
                continue
            gt = cv2.resize(gray_tpl0, (nw, nh), interpolation=cv2.INTER_AREA
                            if s < 1 else cv2.INTER_LINEAR)
        hit = _match_once(gray_scene, gt)
        if not hit:
            continue
        score, x, y, w, h = hit
        if best is None or score > best[0]:
            best = (score, x + off_x, y + off_y, w, h, s)
        if score >= 0.97:
            break
    if not best or best[0] < threshold:
        return None
    score, x, y, w, h, s = best
    return Rect(x, y, w, h, score=score)


# ── 定位 / 点击 ─────────────────────────────────────────────────────────
def locate(app, name: str, form: str = "default",
           threshold: float = DEFAULT_THRESHOLD, scene=None):
    """
    在 Forms 窗口中定位语义元素 name。
    返回 Rect（相对窗口图像）或 None。
    """
    import cv2
    store = TemplateStore()
    tpls = store.templates(form)
    if name not in tpls:
        _log(f"模板库「{form}」里没有「{name}」（已有: {list(tpls)[:8]}）")
        return None
    if scene is None:
        scene = capture(app)
    if scene is None:
        return None
    scene_arr = cv2.cvtColor(np.array(scene), cv2.COLOR_RGB2BGR)
    tpl_arr = imread_unicode(tpls[name], cv2.IMREAD_UNCHANGED)
    if tpl_arr is None:
        return None
    roi = store.roi_for(form, name, (scene_arr.shape[1], scene_arr.shape[0]))
    rect = match_template(scene_arr, tpl_arr, threshold=threshold, roi=roi)
    if rect:
        rect.name = name
        _log(f"命中「{name}」: {rect}")
    else:
        _log(f"未命中「{name}」（置信度不足）")
    return rect


def locate_all(app, form: str = "default", threshold: float = DEFAULT_THRESHOLD):
    """一次截图，定位模板库中全部元素 -> {name: Rect}"""
    import cv2
    store = TemplateStore()
    tpls = store.templates(form)
    if not tpls:
        return {}
    scene = capture(app)
    if scene is None:
        return {}
    scene_arr = cv2.cvtColor(np.array(scene), cv2.COLOR_RGB2BGR)
    out = {}
    for name, path in tpls.items():
        tpl = imread_unicode(path, cv2.IMREAD_UNCHANGED)
        if tpl is None:
            continue
        roi = store.roi_for(form, name, (scene_arr.shape[1], scene_arr.shape[0]))
        r = match_template(scene_arr, tpl, threshold=threshold, roi=roi)
        if r:
            r.name = name
            out[name] = r
    return out


def click_rect(app, rect: Rect, dx: float = 0.5, dy: float = 0.5):
    """
    点击相对窗口图像的矩形（dx/dy 为矩形内比例，默认中心）。
    用窗口实时屏幕位置换算绝对坐标 → 位置无关。
    """
    try:
        from pywinauto import mouse
    except Exception as e:
        _log(f"无法导入 mouse: {e}")
        return False
    wr = window_rect(app)
    if wr is None:
        _log("读不到窗口矩形，无法换算屏幕坐标")
        return False
    left, top = wr[0], wr[1]
    cx = left + rect.x + int(rect.w * dx)
    cy = top + rect.y + int(rect.h * dy)
    try:
        app.window.set_focus()
        time.sleep(0.25)
    except Exception:
        pass
    mouse.move(coords=(cx, cy))
    time.sleep(0.12)
    mouse.click(button="left", coords=(cx, cy))
    _log(f"点击「{rect.name}」屏幕坐标 ({cx}, {cy}) "
         f"= 窗口({left},{top}) + 相对({rect.x},{rect.y})")
    return True


def click(app, name: str, form: str = "default",
          threshold: float = DEFAULT_THRESHOLD, settle: float = 0.6,
          retries: int = 2):
    """定位并点击一个语义元素（失败会重新置前窗口再试）"""
    rect = None
    for attempt in range(retries):
        rect = locate(app, name, form, threshold)
        if rect is not None:
            break
        if attempt < retries - 1:
            _log(f"重试定位「{name}」（第 {attempt + 2} 次）")
            focus_window(app, settle=1.0)
    if rect is None:
        return False
    ok = click_rect(app, rect)
    time.sleep(settle)
    return ok


# ── OCR（可选增强）─────────────────────────────────────────────────────
_ocr_engine = {"ready": False, "engine": None}


def get_ocr():
    """
    返回 OCR 引擎（RapidOCR，CPU，无需 torch）；未安装返回 None。
    安装：pip install rapidocr-onnxruntime
    """
    if _ocr_engine["ready"]:
        return _ocr_engine["engine"]
    _ocr_engine["ready"] = True
    try:
        from rapidocr_onnxruntime import RapidOCR
        _ocr_engine["engine"] = RapidOCR()
        _log("OCR 引擎就绪（RapidOCR）")
    except Exception as e:
        _log(f"OCR 不可用（可选安装 rapidocr-onnxruntime）: {e}")
        _ocr_engine["engine"] = None
    return _ocr_engine["engine"]


def ocr_text(img, region: Rect = None):
    """对图像（或图像中某矩形）做 OCR，返回 [(text, score, (x,y,w,h)), ...]"""
    import cv2
    eng = get_ocr()
    if eng is None or img is None:
        return []
    arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    if region is not None:
        x0, y0, x1, y1 = region.box
        arr = arr[max(0, y0):y1, max(0, x0):x1]
    try:
        result, _ = eng(arr)
    except Exception as e:
        _log(f"OCR 失败: {e}")
        return []
    out = []
    for item in (result or []):
        try:
            box, text, score = item[0], item[1], item[2]
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            out.append((text, float(score),
                        (int(min(xs)), int(min(ys)),
                         int(max(xs) - min(xs)), int(max(ys) - min(ys)))))
        except Exception:
            continue
    return out
