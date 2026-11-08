# -*- coding: utf-8 -*-
"""erp_jws - 用 Java Web Start 直接启动 EBS Forms，绕开浏览器（备用链路）。

背景（2026-11-04 实测确认）：
  * IE11（COM 自动化）**完全可用**——但仅在 360 安全卫士的「防劫持」内核驱动
    （`360AntiHijack64.sys` 等）未拦截时才行。实测发现：360 运行时，该内核驱动
    会在内核态静默拦截 `iexplore.exe` 启动（返回码 1、无崩溃日志），导致
    `InternetExplorer.Application` COM 创建失败（`E_NOINTERFACE`）。注册表、DLL
    注入、TreatAs、IFEO 全部干净，根因就是常驻内核驱动，退出 360 浏览器本身没用
    （驱动独立于浏览器进程常驻）。
  * 本模块（JNLP/javaws）是**无 COM 主链路 / 360 运行时的首选**：纯 HTTP 登录
    （urllib + 老 TLS，不碰 iexplore.exe）→ 抓 RF.jsp applet 参数 → 本地生成
    JNLP → `javaws` 启动。拿到的窗口同样是 `SunAwtFrame`，现有 FormsApp 驱动可
    原样复用。已实测：360 运行中纯 HTTP 登录稳定成功，javaws 能拉起真实业务界面
    （「MRP 计划员工作台」工厂列表）。
  * 注意：Forms 服务器 `erp2.whirlpool-china.com:9001` 依赖内网 DNS 解析，若当前
    网络环境解析不到该域名，applet 会停在启动图或几秒后退窗——这是网络/DNS 问题，
    与 360 及本代码无关。

网络注意：EBS 只认老 TLS（1.0/1.1），必须放开 JRE 的旧 TLS / 旧加密套件
（见 ensure_security_override），否则连不上 forms 服务器。
"""
import html as htmlmod
import http.cookiejar
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from erp_common import ERP_USERNAME, get_erp_password, safe_print

BASE = "https://erp.whirlpool-china.com:4446"
LOGIN_URL = BASE + "/OA_HTML/AppsLogin"
LOGS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
IDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "erp_forms_ids.json")

JAVAWS_CANDIDATES = (
    r"C:\Program Files (x86)\Java\jre1.8.0_191\bin\javaws.exe",
    r"C:\Program Files\Java\jre1.8.0_191\bin\javaws.exe",
    r"C:\Program Files (x86)\Java\jre1.8.0_191\bin\jp2launcher.exe",
)

#: 旧 TLS 覆盖文件路径（launch() 会按需生成）
_SECURITY_OVERRIDE = os.path.join(LOGS, "java.security.override")

UA = "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko"

#: 「更改组织」表单。RF.jsp 只需要这一张：进 Forms 之后一切都在 Forms 里导航。
#: username=hsa697 的 resp_id/resp_appl_id 固定为 51318/201，可用 erp_forms_ids.json 覆盖。
DEFAULT_IDS = {"function_id": 261, "resp_id": 51318, "resp_appl_id": 201}


def log(msg):
    safe_print(msg)


# ── HTTP 会话 ───────────────────────────────────────────────────────────
def _opener():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1
    ctx.set_ciphers("DEFAULT@SECLEVEL=0")
    ctx.options |= 0x40000
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar),
        urllib.request.HTTPSHandler(context=ctx),
    )
    op.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN")]
    return op, jar


def _decode(raw):
    for enc in ("utf-8", "gbk"):
        try:
            s = raw.decode(enc)
        except Exception:
            continue
        if re.search(r"[\u4e00-\u9fff]", s):
            return s
    return raw.decode("latin-1", "replace")


def _get(op, url, timeout=60):
    with op.open(url, timeout=timeout) as r:
        return _decode(r.read()), r.geturl()


def _post(op, url, pairs, timeout=90):
    body = urllib.parse.urlencode(pairs, encoding="gbk").encode()
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with op.open(req, timeout=timeout) as r:
        return _decode(r.read()), r.geturl()


def login(password=None):
    """HTTP 登录 OAF，成功返回 (opener, jar, home_url)。失败抛 RuntimeError。"""
    pwd = password or get_erp_password()
    if not pwd:
        raise RuntimeError("未取到 ERP 密码（erp_secure_config 未初始化）")
    op, jar = _opener()
    page, final = _get(op, LOGIN_URL)
    m = re.search(r'<form[^>]*action="([^"]+)"', page, re.I)
    if not m:
        raise RuntimeError("登录页没有表单 action（网络或地址不对）")
    action = urllib.parse.urljoin(final, m.group(1).replace("&amp;", "&"))

    d = {}
    for mm in re.finditer(r"<input[^>]*>", page, re.I):
        tag = mm.group(0)
        if "hidden" not in tag.lower():
            continue
        nm = re.search(r'name="([^"]+)"', tag)
        vl = re.search(r'value="([^"]*)"', tag)
        if nm:
            d[nm.group(1)] = vl.group(1) if vl else ""
    tok = re.search(r"_FORM_SUBMIT_BUTTON':'([^']+)'", page)
    if not tok:
        raise RuntimeError("登录页没有 _FORM_SUBMIT_BUTTON 令牌")
    d["_FORM_SUBMIT_BUTTON"] = tok.group(1)
    d.pop("Cancel$$unvalidated", None)      # 带了它会被当成「取消」
    d["usernameField"] = ERP_USERNAME
    d["passwordField"] = pwd

    home, home_url = _post(op, action, list(d.items()))
    if "OAHOMEPAGE" not in home_url and "OAFunc" not in home_url:
        raise RuntimeError(f"登录未成功，落在 {home_url[:120]}")
    if re.search(r"[Ll]oginPG|口令.*错误|密码.*错误", home_url + home):
        raise RuntimeError("登录被拒（账号/口令错误）")
    log(f"  [jws] 已登录 {ERP_USERNAME} -> {home_url[:70]}")
    return op, jar, home_url


def load_ids():
    ids = dict(DEFAULT_IDS)
    try:
        with open(IDS_FILE, "r", encoding="utf-8") as f:
            ids.update(json.load(f))
    except Exception:
        pass
    return ids


def fetch_applet(op, ids=None):
    """取更改组织表单的 RF.jsp，返回 (html, [ (name, value) ], [jar ... ])。"""
    ids = ids or load_ids()
    url = (f"{BASE}/OA_HTML/RF.jsp?function_id={ids['function_id']}"
           f"&resp_id={ids['resp_id']}&resp_appl_id={ids['resp_appl_id']}"
           "&security_group_id=0&lang_code=ZHS")
    page, final = _get(op, url)
    i = page.lower().find("<applet")
    if i < 0:
        raise RuntimeError(f"RF.jsp 里没有 applet（{len(page)} 字节）")
    seg = page[i:]
    j = seg.lower().find("</applet>")
    seg = seg[: j + 9] if j > 0 else seg[:8000]

    params = []
    for m in re.finditer(r"<PARAM\s+name=[\"']?([A-Za-z0-9_]+)[\"']?\s+value=\"(.*?)\"\s*>",
                         seg, re.I | re.S):
        params.append((m.group(1), htmlmod.unescape(m.group(2))))
    if not params:
        raise RuntimeError("applet 标签里解析不到 PARAM")

    arc = re.search(r'archive="([^"]*)"', seg, re.I)
    jars = []
    if arc:
        jars = [a.strip().lstrip("/") for a in arc.group(1).split(",") if a.strip()]
    return page, params, jars


def build_jnlp(params, jars, path=None):
    path = path or os.path.join(LOGS, "ebs_forms.jnlp")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    jsec = "\n".join('        <jar href="%s" download="eager" main="false"/>' % j
                     for j in jars)
    par = "\n".join('        <param name="%s" value="%s"/>' % (
        n, htmlmod.escape(v, quote=True)) for n, v in params)
    jnlp = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<jnlp spec="1.0+" codebase="{BASE}/">\n'
        "    <information>\n"
        "        <title>Oracle Applications</title>\n"
        "        <vendor>Oracle</vendor>\n"
        "    </information>\n"
        "    <security>\n"
        "        <all-permissions/>\n"
        "    </security>\n"
        "    <resources>\n"
        '        <j2se version="1.8+"/>\n'
        f"{jsec}\n"
        "    </resources>\n"
        '    <applet-desc main-class="oracle.apps.fnd.formsClient.FormsLauncher"\n'
        '                 name="FormsApplet" width="995" height="700">\n'
        f"{par}\n"
        "    </applet-desc>\n"
        "</jnlp>\n"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(jnlp)
    return path


def find_javaws():
    for p in JAVAWS_CANDIDATES:
        if os.path.exists(p):
            return p
    raise RuntimeError("找不到 javaws.exe（需要 JRE 8）")


# ── Java「安全警告」对话框自动确认 ──────────────────────────────────────
# EBS 的签名证书已过期，javaws 每次启动都会弹
#   「是否要运行此应用程序？ … 我接受风险并希望运行此应用程序(I) [运行(R)] [取消]」
# 不处理就一直等到超时。deployment.expiration.check.enabled=false 通常能压掉它，
# 但换机器/换 JRE 又会冒出来，所以这里再兜一层：Alt+I 勾选 + Enter 运行。
SEC_WARN_TITLES = ("安全警告", "安全", "Security Warning", "Security", "警告")


def _find_sec_warn():
    """找 Java 的阻塞弹窗：SunAwtDialog（安全警告）或 #32770（Java Update 等）。"""
    import win32gui
    found = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        cls = win32gui.GetClassName(h)
        t = win32gui.GetWindowText(h) or ""
        if cls == "SunAwtDialog" and any(
                k in t for k in ("安全警告", "警告", "Security", "安全")):
            found.append(h)
        elif cls == "#32770" and "Java" in t:
            found.append(h)

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        pass
    return found[0] if found else None


def find_security_warning():
    return _find_sec_warn()


def _click_xy(x, y):
    from pywinauto import mouse
    mouse.move(coords=(x, y))
    time.sleep(0.12)
    mouse.click(button="left", coords=(x, y))


def _dialog_tokens(hwnd):
    """截对话框自身图像（pywinauto）+ OCR，返回 (img, [(text, Rect)])。

    ⚠️ 不能用 win32gui.GetWindowRect + ImageGrab 截 —— AWT 弹窗的矩形给得很偏，
       截出来是后面的网页，只露半个对话框。pywinauto 的 capture_as_image 正常。
    """
    from pywinauto import Desktop
    from erp_flow_org import ocr_hits
    w = Desktop(backend="win32").window(handle=hwnd)
    img = w.capture_as_image()
    return img, [(t, r) for t, s, r in ocr_hits(img)]


#: 点这些词 = 「运行 / 不更新 / 继续」；点「更新 / 立即更新 / 下载」会把流程带沟里
_PROMPT_OK = ("运行", "稍后", "以后", "不是现在", "继续", "确定", "关闭")


def accept_security_warning(save_png=None):
    """处理 Java 启动弹窗（证书过期的「安全警告」、Java Update 提醒等）。

    做法：截对话框 → OCR → 勾「我接受风险」→ 点「运行(R)」/「稍后」。

    ⚠️ 绝不能用回车：这个框的默认按钮是「取消」，一按 Enter javaws 就以 rc=0
       安静退出，现象像"等不到 applet"，很容易误判成网络问题。
    """
    import win32gui

    h = _find_sec_warn()
    if h is None:
        return False

    for rnd in range(4):
        if not (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h)):
            return True
        try:
            win32gui.SetForegroundWindow(h)
        except Exception:
            pass
        time.sleep(0.7)
        try:
            img, toks = _dialog_tokens(h)
        except Exception as e:
            log(f"  [WARN] 弹窗截图失败：{e}")
            return False
        if save_png and rnd == 0:
            try:
                img.save(save_png)
            except Exception:
                pass

        left, top = win32gui.GetWindowRect(h)[:2]
        dirty = ",".join(t for t, _ in toks)[:70]
        log(f"  [jws] Java 弹窗内容：{dirty}")

        chk = next((r for t, r in toks if "我接受风险" in t.replace(" ", "")), None)
        # 勾选框：文案左边那个小方块比文字本身更准，点文字也能切，但方块更保险
        if chk is not None:
            cx, cy = left + max(6, chk.x - 20), top + chk.y + chk.h // 2
            log(f"  [jws] 勾选『我接受风险』({cx},{cy})")
            _click_xy(cx, cy)
            time.sleep(0.6)

        # 找按钮：只认「短标签」且以关键词开头，避免把提问句
        # 「是否要运行此应用程序?」里的「运行」当成按钮（踩过：点它没反应）
        best, kw = None, None
        for t, r in toks:
            tt = t.replace(" ", "").strip()
            if len(tt) > 10:
                continue
            for k in _PROMPT_OK:
                if tt.startswith(k):
                    if best is None or r.y > best.y:      # 按钮都在底部，取最靠下的
                        best, kw = r, k
                    break
        target = best
        if target is None:
            log("  [WARN] 弹窗里没有可点的按钮（见下），10 秒后重试")
            for t, _ in toks[:12]:
                log(f"      {t!r}")
            time.sleep(10)
            continue

        bx, by = left + target.x + target.w // 2, top + target.y + target.h // 2
        log(f"  [jws] 点击『{kw}』({bx},{by})")
        _click_xy(bx, by)
        time.sleep(2.0)
        if not (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h)):
            log("  [OK] 弹窗已通过，开始加载 applet")
            return True

    gone = not (win32gui.IsWindow(h) and win32gui.IsWindowVisible(h))
    log(f"  [{'OK' if gone else 'WARN'}] 弹窗处理结束"
        f"（{'已消失' if gone else '仍在'}）")
    return gone




def launch(jnlp_path):
    exe = find_javaws()
    env = dict(os.environ)
    ov = ensure_security_override()
    env["_JAVA_OPTIONS"] = f"-Djava.security.properties={ov}"
    log(f"  [jws] 放开旧 TLS（java.security 覆盖：{os.path.basename(ov)}）")

    # 关键：把 javaws 彻底脱离父进程的控制台与进程组，
    # 否则父脚本一退出（尤其后台任务被回收时）会连 javaw 一起杀掉，
    # Forms 窗口刚连上就“断链”消失。
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 1  # SW_SHOWNORMAL
    kwargs = dict(
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=env, creationflags=0,
        startupinfo=si,
    )
    if sys.platform == "win32":
        # DETACHED_PROCESS 让子进程无控制台；CREATE_NEW_PROCESS_GROUP 让它
        # 不隶属于父进程组，父退出/被任务回收时不会被一起杀。
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        )
    proc = subprocess.Popen([exe, jnlp_path], **kwargs)
    log(f"  [jws] javaws pid={proc.pid}  ({os.path.basename(exe)})，已脱离父进程")
    return proc


def ensure_security_override():
    """生成 java.security 覆盖文件：放开旧 TLS / 旧加密套件。

    EBS 只认 TLS1.0 + RC4/3DES，而 JRE 8u191 默认把 RC4 / DES / 3DES_EDE_CBC
    全禁了 → applet 连不上 forms 服务器，现象是「窗口停在 ORACLE 启动图，
    几十秒后自己退出」。改 Program Files 下的 java.security 要管理员权限，
    所以用 -Djava.security.properties 覆盖 + _JAVA_OPTIONS 注入
    （applet 的 javaw 进程会继承启动它的环境）。
    """
    os.makedirs(LOGS, exist_ok=True)
    body = (
        "# 由 erp_jws.py 生成：放开旧 TLS / 旧加密套件，供惠而浦 EBS 使用\n"
        "jdk.tls.disabledAlgorithms=\n"
        "jdk.certpath.disabledAlgorithms=\n"
        "jdk.tls.client.protocols=TLSv1,TLSv1.1,TLSv1.2\n"
        "jdk.tls.legacyAlgorithms=RC4, DES, 3DES_EDE_CBC, MD5withRSA, NULL\n"
    )
    try:
        with open(_SECURITY_OVERRIDE, "r", encoding="utf-8") as f:
            if f.read() == body:
                return _SECURITY_OVERRIDE
    except Exception:
        pass
    with open(_SECURITY_OVERRIDE, "w", encoding="utf-8") as f:
        f.write(body)
    return _SECURITY_OVERRIDE


def wait_applet(before=(), timeout=200, poll=5.0):
    """等 javaws 把 applet 窗口画出来；返回 (hwnd, title) 或 (None, None)。

    期间自动确认 Java「安全警告」对话框（证书过期那种）。
    """
    import erp_navigator
    before = set(before or ())
    t0 = time.time()
    last_note = 0
    warned = 0
    while time.time() - t0 < timeout:
        # 先处理安全警告：对话框在的时候，窗口可能已经存在但还没开始渲染
        if warned < 4 and accept_security_warning(
                save_png=os.path.join(LOGS, "jws_secwarn.png")):
            warned += 1
            continue
        snap = erp_navigator.snapshot_forms_windows()
        new = [h for h in snap if h not in before]
        if new:
            h = new[0]
            log(f"  [jws] applet 就绪 hwnd={h} ({int(time.time() - t0)}s)")
            return h, snap[h]
        time.sleep(poll)
        if time.time() - t0 - last_note > 30:
            last_note = time.time() - t0
            log(f"  [jws] 等待 applet… {int(last_note)}s"
                "（首次要下载 9 个 jar，约 60~90s）")
            if warned >= 3:
                log("  [WARN] 安全警告已连点 3 次仍没起来，请人工看一眼桌面")
    return None, None



def start(timeout=200, password=None):
    """一步到位：HTTP 登录 → 取参数 → 生成 JNLP → javaws → 等窗口。

    返回 dict(session=opener, hwnd=..., title=..., jnlp=...)。
    """
    import erp_navigator
    op, _jar, home_url = login(password)
    _page, params, jars = fetch_applet(op)
    jp = build_jnlp(params, jars)
    log(f"  [jws] JNLP 已生成 {jp}（{len(params)} 参数 / {len(jars)} jar）")
    before = set(erp_navigator.snapshot_forms_windows())
    launch(jp)
    hwnd, title = wait_applet(before, timeout=timeout)
    return {"session": op, "hwnd": hwnd, "title": title, "jnlp": jp,
            "home_url": home_url}


def logout(op=None):
    """HTTP 注销（javaws 起的 applet 不经过浏览器，只能这样退）。"""
    if op is None:
        return False
    for url in (BASE + "/OA_HTML/AppsLogout", BASE + "/OA_HTML/OA.jsp?OAFunc=OALOGOUT"):
        try:
            _get(op, url, timeout=30)
            log("  [jws] 已 HTTP 注销")
            return True
        except Exception:
            continue
    log("  [WARN] HTTP 注销失败（会话会自行超时）")
    return False


if __name__ == "__main__":
    r = start()
    log(f"applet={r['hwnd']} title={r['title']}")
