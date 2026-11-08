#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_navigator - 通过 IE11 进入指定职责/功能并拉起 Oracle Forms

链路（2026-10 实测全通）：
  IE11 登录
  -> 主页点击职责链接（href="#"，onclick 展开功能树）
  -> 点击功能链接（javascript:launchForm('...RF.jsp?function_id=...')）
  -> 新 IE 窗口加载 /forms/frmservlet -> appsbase.htm（JInitiator 架构 applet 页）
  -> Java 8 插件（本机 jre1.8.0_191 32位）运行 FormsLauncher applet
  -> 弹出独立 Java 窗口（class=SunAwtFrame，标题「Oracle Applications - 惠而浦（中国）ERP系统」）

已验证实例：
  职责「PO,SANYO合肥三洋物料计划员」
  功能「MRP计划员工作台」= function_id=1908, resp_id=51318, form MRPFPPWB-394

注意：
  - 该 EBS 的 Forms 是 Java Applet（非 JNLP/Web Start），服务器不返回 JNLP，
    本机为 JRE（无 appletviewer）—— IE11 + Java 插件是实测唯一可行路径。
  - Java AWT 窗口对 UIA 暴露极差（只能看到 TitleBar），内部为自绘控件，
    自动化驱动请用键盘/坐标方式，参见 erp_forms.FormsApp。
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import win32com.client  # noqa: E402
import win32gui  # noqa: E402

import erp_ie11  # noqa: E402
from erp_ie11 import is_logged_in, page_title  # noqa: E402

# Forms 窗口特征（实测：Java AWT 顶层框架）
FORMS_WINDOW_CLASS = "SunAwtFrame"
FORMS_WINDOW_TITLE_MARK = "Oracle Applications"

LAUNCH_PREFIX = "javascript:launchForm("


class IeBroken(RuntimeError):
    """IE 实例已损坏（第二次导航后崩溃 / RPC 不可用）——需要重建并重新登录"""


def _log(msg):
    erp_ie11._log(msg)


# ── IE DOM 通用 ────────────────────────────────────────────────────────
def _iter_links(doc):
    """遍历 <a>，yield (index, element, text, href)，容错跳过坏元素。"""
    links = doc.getElementsByTagName("a")
    for i in range(links.length):
        try:
            el = links.item(i)
            if el is None:
                break
            t = (el.innerText or "").strip().replace("\r\n", " ")
            try:
                h = el.href or ""
            except Exception:
                h = ""
            yield i, el, t, h
        except Exception:
            continue


# 主页（职责列表所在页）备用入口：不带一次性 oas token，会话有效时可直接进
HOME_URL_PLAIN = (
    "https://erp.whirlpool-china.com:4446/OA_HTML/OA.jsp"
    "?page=/oracle/apps/fnd/framework/navigate/webui/NewHomePG"
    "&homePage=Y&retainAM=Y&addBreadCrumb=N&OAMC=G&WFEBizWorklist=Y&oapc=2"
)


def _has_resp_links(ie) -> bool:
    """是否停在主页（主页职责链接的 href 以 '#' 结尾）"""
    doc = ie.Document
    try:
        links = doc.getElementsByTagName("a")
        for i in range(links.length):
            try:
                el = links.item(i)
                if el is None:
                    break
                h = el.href or ""
                t = (el.innerText or "").strip()
            except Exception:
                continue
            if h.endswith("#") and t:
                return True
    except Exception:
        pass
    return False


def _wait_home(ie, timeout: int = 20) -> bool:
    """
    等待主页就绪。

    ⚠️ 主页的职责列表是**延迟渲染**的：IE 导航完成（ReadyState=4）时职责链接
    往往还没进 DOM，直接查会得到"主页未找到职责链接"的假失败（实测踩过）。
    故这里轮询等待"职责链接出现"或"主页特征文本出现"。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if _has_resp_links(ie):
                return True
        except Exception:
            pass
        try:
            txt = erp_ie11.body_text(ie)
        except Exception:
            txt = ""
        if any(m in txt for m in ("主菜单", "Oracle Applications 主页",
                                  "Main Menu", "Logged In")):
            # 特征文本已出，但职责链接可能还在渲染，再等一小会儿
            if _has_resp_links(ie):
                return True
        time.sleep(1)
    # 兜底：特征文本在就算主页（职责可能是别的责任集）
    try:
        txt = erp_ie11.body_text(ie)
        return any(m in txt for m in ("主菜单", "Oracle Applications 主页",
                                      "Main Menu", "Logged In"))
    except Exception:
        return False


def _wait_for_resp(ie, resp_name: str, timeout: int = 20) -> bool:
    """
    轮询等待职责链接出现。

    主页的职责列表是延迟渲染的：登录判定通过时它可能还没进 DOM，
    直接查会得到"主页未找到职责链接"的假失败。故先轮询等待。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            for _, _, t, _ in _iter_links(ie.Document):
                if resp_name in t:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def ensure_homepage(ie, timeout: int = 30) -> bool:
    """
    确保 IE 停在 EBS 主页（职责列表页）。

    复用已有会话时 IE 可能停留在某个子页面（如上次打开的 Navigator），
    此时职责链接不存在、点职责必然失败，故先回主页。
    """
    if _has_resp_links(ie):
        return True
    for url in (erp_ie11.ERP_HOME_URL, HOME_URL_PLAIN):
        _log(f"[导航] 当前不在主页，返回主页: {url[:70]}...")
        try:
            ie.Navigate(url)
        except Exception as e:
            _log(f"[导航] 导航异常: {e}")
            raise IeBroken(f"导航主页失败: {e}")
        erp_ie11.wait_ready(ie, timeout)
        # ⚠️ 同一 IE 实例内第二次 Navigate 会让 IE 崩溃（RPC 不可用）
        if not erp_ie11._dom_ok(ie, tries=3, delay=1.0):
            raise IeBroken("返回主页后 IE DOM 不可访问，实例已损坏")
        # 主页职责列表延迟渲染，必须轮询等它出来，不能只看一次
        if _wait_home(ie, timeout=20):
            _log("[导航] 已回到主页")
            return True
    return False


def find_resp_node(ie, resp_name: str):
    """找到主页上对应职责的 <LI> 节点（未找到返回 None）"""
    try:
        lis = ie.Document.getElementsByTagName("li")
    except Exception:
        return None
    for i in range(lis.length):
        try:
            li = lis.item(i)
            if li is None:
                break
            if resp_name in (li.innerText or ""):
                return li
        except Exception:
            continue
    return None


def resp_function_links(ie, li) -> list:
    """
    取出某个职责 <LI> 下的功能链接（javascript:launchForm(...)）。
    已展开的职责无需点击即可直接读取 —— 这是最稳的方式（点击职责会点崩 IE）。
    """
    out = []
    if li is None:
        return out
    try:
        links = li.getElementsByTagName("a")
    except Exception:
        return out
    for i in range(links.length):
        try:
            el = links.item(i)
            if el is None:
                break
            h = el.href or ""
            if not h.startswith(LAUNCH_PREFIX):
                continue
            t = (el.innerText or "").strip().replace("\r\n", " ")
            url = h[len(LAUNCH_PREFIX):].rstrip(")").strip().strip("'")
            out.append({"name": t, "url": url, "el": el})
        except Exception:
            continue
    return out


def expand_responsibility(ie, resp_name: str, timeout: int = 25,
                          allow_click: bool = True) -> bool:
    """
    定位职责并取得其功能列表。

    ⚠️ 实测（2026-10-21）：对职责 <A> 调用 click() 会让 IE 进程崩溃
    （随后一律 'RPC 服务器不可用'）。EBS 的职责菜单树是**服务端按会话保持
    展开状态**的，所以这里的策略是：
      1) 先找职责 <LI> 节点；
      2) 若其下已有 javascript:launchForm(...) 功能链接 → **直接读取，不点击**；
      3) 只有确实没有功能链接时，才尝试点击展开（allow_click）。

    返回 True=已取得该职责（功能列表可用）。
    """
    t0 = time.time()
    li = None
    while time.time() - t0 < timeout:
        li = find_resp_node(ie, resp_name)
        if li is not None:
            break
        time.sleep(1)
    if li is None:
        # 职责列表延迟渲染 → 先回主页再找
        _log(f"[导航] 当前页未见职责「{resp_name}」，先回主页再重试")
        if ensure_homepage(ie):
            t0 = time.time()
            while time.time() - t0 < 15:
                li = find_resp_node(ie, resp_name)
                if li is not None:
                    break
                time.sleep(1)
        if li is None:
            avail = list_responsibilities(ie)
            _log(f"[FAIL] 主页未找到职责链接: {resp_name}")
            if avail:
                _log(f"[提示] 主页当前可见职责: {avail}")
            return False

    funcs = resp_function_links(ie, li)
    if funcs:
        _log(f"[导航] 职责「{resp_name}」已展开，直接读取到 {len(funcs)} 个功能"
             f"（无需点击，避免点崩 IE）")
        return True

    if not allow_click:
        _log(f"[FAIL] 职责「{resp_name}」未展开且未允许点击展开")
        return False

    # 未展开：点击 <LI> 里的展开图标（比点 <A> 安全一点）
    _log(f"[导航] 职责「{resp_name}」未展开，尝试点击展开 ...")
    try:
        target = None
        imgs = li.getElementsByTagName("img")
        for i in range(imgs.length):
            try:
                im = imgs.item(i)
                if im is not None and (im.alt or "").lower() == "expand":
                    target = im
                    break
            except Exception:
                continue
        if target is None:
            anchors = li.getElementsByTagName("a")
            target = anchors.item(0) if anchors.length else None
        if target is None:
            _log("[FAIL] 职责节点里找不到可点击的展开元素")
            return False
        n_before = len(resp_function_links(ie, li))
        target.click()
        t0 = time.time()
        while time.time() - t0 < timeout:
            time.sleep(1)
            if not erp_ie11._dom_ok(ie, tries=1, delay=0.2):
                raise IeBroken("点击职责展开后 IE 崩溃")
            n_now = len(resp_function_links(ie, li))
            if n_now > n_before:
                _log(f"[导航] 职责已展开（功能链接 {n_before} -> {n_now}）")
                return True
    except IeBroken:
        raise
    except Exception as e:
        _log(f"[WARN] 点击展开失败: {e}")
        return False
    _log("[WARN] 点击职责后功能链接未增加（可能本已展开，继续尝试找功能）")
    return True


def list_responsibilities(ie) -> list:
    """列出主页当前可见的职责名（href='#' 的链接文字）"""
    out = []
    try:
        for _, _, t, h in _iter_links(ie.Document):
            if h.endswith("#") and t and t not in out:
                out.append(t)
    except Exception:
        pass
    return out


def read_function_url(ie, func_name: str, resp_name: str = ""):
    """
    **只读**取得功能的 launchForm URL（不点击）。
    好处：不会触发 window.open —— 那个新窗口会被系统默认浏览器（360）接管，
    导致 applet 跑不起来。我们改为拿到 URL 后自己开 IE 窗口导航过去。
    """
    cand = []
    if resp_name:
        li = find_resp_node(ie, resp_name)
        cand = resp_function_links(ie, li)
    else:
        for _, el, t, h in _iter_links(ie.Document):
            if h.startswith(LAUNCH_PREFIX):
                cand.append({"name": t,
                             "url": h[len(LAUNCH_PREFIX):].rstrip(")").strip().strip("'")})
    first_hit = None
    for f in cand:
        if f["name"] == func_name:
            return f["url"]
        if first_hit is None and func_name in f["name"]:
            first_hit = f
    return first_hit["url"] if first_hit else None


def open_forms_window(url: str, visible: bool = True, width: int = 1366,
                      height: int = 900):
    """
    新开一个 IE 窗口并导航到 RF.jsp（Forms 启动地址）。
    这样 applet 一定跑在 IE11 的 Java 插件里，不受默认浏览器影响。
    返回 ie 对象（失败 None）。
    """
    import win32com.client
    try:
        ie2 = win32com.client.Dispatch("InternetExplorer.Application")
        ie2.Visible = visible
        try:
            ie2.Width = width
            ie2.Height = height
        except Exception:
            pass
        erp_ie11.register_instance(ie2)
        _log(f"[导航] 新开 IE 窗口加载 Forms: {url[:140]}")
        ie2.Navigate(url)
        return ie2
    except Exception as e:
        _log(f"[FAIL] 新开 IE 窗口失败: {e}")
        return None


def list_functions(ie, func_filter: str = "", resp_name: str = "") -> list:
    """
    返回当前职责下的全部功能：
      [{"name": 功能名, "url": launchForm 里的完整 URL}]
    resp_name 非空时只取该职责下的功能（不串到别的职责）。
    func_filter 非空时按子串过滤功能名。
    """
    out = []
    if resp_name:
        li = find_resp_node(ie, resp_name)
        for f in resp_function_links(ie, li):
            if func_filter and func_filter not in f["name"]:
                continue
            out.append({"name": f["name"], "url": f["url"]})
        return out
    for _, _, t, h in _iter_links(ie.Document):
        if h.startswith(LAUNCH_PREFIX):
            if func_filter and func_filter not in t:
                continue
            url = h[len(LAUNCH_PREFIX):]
            url = url.rstrip(")").strip().strip("'").strip()
            out.append({"name": t, "url": url})
    return out


def click_function(ie, func_name: str, resp_name: str = ""):
    """
    点击功能链接触发 launchForm。返回完整 URL（找不到返回 None）。
    精确匹配优先，找不到再退回子串匹配。

    ⚠️ 只点**功能**链接（javascript:launchForm → window.open 新窗口），
       绝不点职责链接（实测那会点崩 IE）。
    """
    cand = []
    if resp_name:
        li = find_resp_node(ie, resp_name)
        cand = resp_function_links(ie, li)
    else:
        for _, el, t, h in _iter_links(ie.Document):
            if h.startswith(LAUNCH_PREFIX):
                url = h[len(LAUNCH_PREFIX):].rstrip(")").strip().strip("'")
                cand.append({"name": t, "url": url, "el": el})

    first_hit = None
    for f in cand:
        if f["name"] == func_name:
            f["el"].click()
            return f["url"]
        if first_hit is None and func_name in f["name"]:
            first_hit = f
    if first_hit:
        _log(f"[导航] 精确匹配未命中，退回子串匹配: {first_hit['name']}")
        first_hit["el"].click()
        return first_hit["url"]
    return None


# ── Forms 窗口探测 ─────────────────────────────────────────────────────
def snapshot_forms_windows() -> dict:
    """枚举当前所有 Forms Java 窗口 {hwnd: title}（class=SunAwtFrame）。"""
    out = {}

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            return
        if cls == FORMS_WINDOW_CLASS and FORMS_WINDOW_TITLE_MARK in title:
            out[hwnd] = title

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return out


def wait_new_forms_window(before: dict, timeout: int = 150):
    """
    轮询等待「新」Forms 窗口出现（applet 加载 + jar 下载可能较慢，默认 150s）。
    返回 (hwnd, title) 或 None。
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(3)
        now = snapshot_forms_windows()
        for hwnd, title in now.items():
            if hwnd not in before:
                return hwnd, title
    return None


def detect_hijacked_windows() -> list:
    """
    检测「被非 IE 浏览器接管」的 ERP 窗口，**仅记录提示，不做任何关闭/结束动作**。

    背景：launchForm 的 window.open 若没落在 IE11 内，系统默认浏览器会接手。
    360 安全浏览器是双核（兼容模式 = IE 内核），真的能把 Java applet 跑起来，
    于是出现「Oracle Applications R12 - 360安全浏览器」这样的窗口。

    处理约定：本技能**不主动使用 360 打开页面**（360 回退已默认禁用），
    但若系统自行把新窗口交给 360，**不干预、不结束其进程**（用户明确要求
    不用管 360 的进程），照常等待 Forms 拉起即可——360 兼容模式能正常跑 applet。

    返回检测到的窗口列表 [(hwnd, class, title)]。
    """
    hijacked = []

    # 只对「浏览器类」窗口报警。
    # ⚠️ 修 2026-10-21 的误报：Forms 窗口（class=SunAwtFrame）标题同样含
    # "Oracle Applications"，早先被当成"被非 IE 浏览器接管"刷了一堆假提示。
    BROWSER_CLASSES = {
        "IEFrame",            # IE11 自身（正常）
        "Chrome_WidgetWin_1", # Chromium 系
        "360se6Frame",        # 360 安全浏览器
        "MozillaWindowClass",  # Firefox
    }

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
            title = win32gui.GetWindowText(hwnd)
        except Exception:
            return
        if cls == FORMS_WINDOW_CLASS:
            return                      # Forms Java 窗口本身，不是浏览器
        if cls in ("IEFrame",):
            return                      # 正常：落在 IE11 内
        if FORMS_WINDOW_TITLE_MARK in title:
            hijacked.append((hwnd, cls, title))

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass

    for hwnd, cls, title in hijacked:
        _log(f"[提示] 新窗口由非 IE 浏览器承载（class={cls}）: {title!r}。"
             "本技能不主动使用其它浏览器，也不干预其进程，继续等待 Forms 拉起。")
    return hijacked


def snapshot_ie_windows() -> dict:
    """枚举所有 IE 窗口 {hwnd: title}（class=IEFrame），用于发现 launchForm 衍生的载体窗口"""
    out = {}

    def _cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        try:
            cls = win32gui.GetClassName(hwnd)
        except Exception:
            return
        if cls == "IEFrame":
            try:
                out[hwnd] = win32gui.GetWindowText(hwnd)
            except Exception:
                out[hwnd] = ""

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        pass
    return out


# ── 端到端 ────────────────────────────────────────────────────────────
def open_function(resp_name: str, func_name: str,
                  visible: bool = True, timeout: int = 150,
                  shot_path: str = "", close_ie: bool = False,
                  reuse_existing: bool = True):
    """
    端到端：登录 -> 读职责功能 -> 拿 launchForm URL -> 自开 IE 窗口加载 Forms
            -> 等 Forms 窗口 -> 返回 FormsApp。

    resp_name 职责名（如 "PO,SANYO合肥三洋物料计划员"）
    func_name 功能名（如 "MRP计划员工作台"）
    reuse_existing 已存在 Forms 窗口时直接复用（实测：同一 JRE 里再起第二个
               applet 会起不来，第二个 Forms 窗口迟迟不出现）。
    close_ie   结束后是否关闭 IE 窗口。
               **默认 False**：Oracle Forms 的 applet 运行在承载它的 IE 进程里，
               关掉 IE 会让刚拉起的 Forms 一起消失，所以默认保留；
               这些窗口已登记，下次运行 open/login 时会自动清理。
               仅当你确认不再需要该 Forms 会话时才设 True（或加 --close-ie）。
    返回 FormsApp（失败返回 None）。
    """
    ie = erp_ie11.open_and_login(visible=visible, lang="ZHS")
    if ie is None:
        return None
    try:
        if not is_logged_in(ie):
            _log(f"[FAIL] 登录失败（title={page_title(ie)!r}）")
            return None

        before = snapshot_forms_windows()
        ie_before = snapshot_ie_windows()
        _log(f"[导航] 当前已有 Forms 窗口 {len(before)} 个")

        from erp_forms import FormsApp

        # 已有 Forms 窗口 → 直接复用（省一次 applet 启动，省 2 分钟）
        if reuse_existing and before:
            hwnd = list(before.keys())[-1]
            _log(f"[导航] 复用已打开的 Forms 窗口: hwnd={hwnd} "
                 f"title={before[hwnd]!r}")
            app = FormsApp()
            if not app.connect_by_hwnd(hwnd):
                return None
            try:
                app.window.set_focus()
            except Exception:
                pass
            if shot_path:
                app.screenshot(shot_path)
            return app

        # IE 实例可能因二次导航崩溃 → 重建实例重新登录后再试一次
        try:
            if not expand_responsibility(ie, resp_name):
                return None
        except IeBroken as e:
            _log(f"[导航] IE 实例损坏（{e}），重建实例并重新登录后重试")
            erp_ie11.close_our_instances()
            ie = erp_ie11.open_and_login(visible=visible, lang="ZHS")
            if ie is None or not is_logged_in(ie):
                _log("[FAIL] 重建后仍无法登录")
                return None
            if not expand_responsibility(ie, resp_name):
                return None

        # 取得功能的 launchForm URL。
        # ⚠️ 不点功能链接（window.open 会被系统默认浏览器 360 接管，applet 起不来），
        #    而是"只读取 URL + 自己开 IE 窗口导航过去"，applet 必定跑在 IE11 里。
        url = read_function_url(ie, func_name, resp_name=resp_name)
        if url is None:
            funcs = [f["name"] for f in list_functions(ie, resp_name=resp_name)]
            _log(f"[FAIL] 职责下未找到功能: {func_name}")
            _log(f"[提示] 该职责可用功能: {funcs}")
            return None
        _log(f"[导航] 功能「{func_name}」launchForm URL: {url[:180]}")

        ie2 = open_forms_window(url, visible=visible)
        if ie2 is None:
            return None

        # 兼容旧路径：万一 JS window.open 也开了窗口，一并登记
        time.sleep(3)
        new_ie = {h: t for h, t in snapshot_ie_windows().items()
                  if h not in ie_before}
        if new_ie:
            erp_ie11.register_hwnds(list(new_ie.keys()))
            _log(f"[登记] 衍生 IE 载体窗口 {len(new_ie)} 个: "
                 f"{list(new_ie.values())[:2]}")
        detect_hijacked_windows()

        hit = wait_new_forms_window(before, timeout=timeout)
        if not hit:
            # 没等到新窗口：若已有旧窗口，提示复用
            now = snapshot_forms_windows()
            if now:
                hwnd = list(now.keys())[-1]
                _log(f"[WARN] 未出现新 Forms 窗口，复用已有窗口 hwnd={hwnd}")
                hit = (hwnd, now[hwnd])
            else:
                _log(f"[FAIL] {timeout}s 内未出现新 Forms 窗口"
                     "（请检查 IE 弹出的 Java 安全提示/证书确认框）")
                return None
        hwnd, title = hit
        _log(f"[OK] Oracle Forms 窗口已拉起: hwnd={hwnd} title={title!r}")

        app = FormsApp()
        if not app.connect_by_hwnd(hwnd):
            return None

        if shot_path:
            app.screenshot(shot_path)
        return app
    finally:
        # ⚠️ 这里**不能**直接关闭 IE/Forms：返回的 FormsApp 还要被调用方使用
        # （识别/点击/读取）。统一由调用方在用完后调用：
        #   erp_ie11.close_all(logout=True)   → 注销 EBS + 关闭 IE（推荐收口）
        #   erp_ie11.close_all(logout=False)  → 只关 IE 不注销
        # 保留窗口的调用方（--keep-ie），退出前跑 `erp_ops.py logout`。
        _log("[导航] 流程结束（IE/Forms 仍开着，归调用方收口）")


def main():
    import argparse
    ap = argparse.ArgumentParser(description="IE11 导航进职责/功能并拉起 Oracle Forms")
    ap.add_argument("responsibility", help="职责名，如: PO,SANYO合肥三洋物料计划员")
    ap.add_argument("function", nargs="?", default="",
                    help="功能名，如: MRP计划员工作台；缺省则仅列出该职责下全部功能")
    ap.add_argument("--timeout", type=int, default=150,
                    help="等待 Forms 窗口秒数（默认 150）")
    ap.add_argument("--shot", default="",
                    help="拉起后对 Forms 窗口截图保存路径")
    ap.add_argument("--keep-ie", dest="keep_ie", action="store_true",
                    help="结束后保留 IE/Forms（默认注销 EBS 并关闭全部 IE）")
    args = ap.parse_args()

    if not args.function:
        ie = erp_ie11.open_and_login(visible=True, lang="ZHS")
        if ie is None or not is_logged_in(ie):
            sys.exit(2)
        try:
            if not expand_responsibility(ie, args.responsibility):
                sys.exit(3)
            funcs = list_functions(ie, resp_name=args.responsibility)
            print(f"职责「{args.responsibility}」下共 {len(funcs)} 个功能:")
            for f in funcs:
                print(f"  - {f['name']}")
                print(f"      {f['url'][:160]}")
        finally:
            # 仅列功能、未拉起 Forms，用完即注销并关 IE
            erp_ie11.close_all(logout=not args.keep_ie)
        return

    shot = args.shot or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "logs", "forms_window.png")
    app = None
    try:
        app = open_function(args.responsibility, args.function,
                            timeout=args.timeout, shot_path=shot,
                            close_ie=not args.keep_ie)
        if app is None:
            sys.exit(4)
        print(f"MEDIA:{os.path.abspath(shot)}")
    finally:
        # 收口：默认注销 EBS + 关闭全部 IE（--keep-ie 才保留）
        erp_ie11.close_all(logout=not args.keep_ie)


if __name__ == "__main__":
    main()
